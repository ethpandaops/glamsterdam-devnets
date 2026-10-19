// Restore already-validated BAL sidecars after checking native canonical headers.
// Writes use Erigon v3.7.1's native API and require an exclusive database open.
package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/erigontech/erigon/common"
	"github.com/erigontech/erigon/common/crypto"
	"github.com/erigontech/erigon/common/log/v3"
	"github.com/erigontech/erigon/db/kv"
	"github.com/erigontech/erigon/db/kv/dbcfg"
	"github.com/erigontech/erigon/db/kv/mdbx"
	"github.com/erigontech/erigon/db/rawdb"
)

const revision = "8c1e3893d77d230720d172f1492d95b5777a862c"

type Report struct {
	Version        int    `json:"version"`
	ClientRevision string `json:"client_revision"`
	Start          uint64 `json:"start"`
	End            uint64 `json:"end"`
	Head           uint64 `json:"head"`
	HeadHash       string `json:"head_hash"`
	StateRoot      string `json:"state_root"`
	Verified       uint64 `json:"verified_records"`
	Missing        uint64 `json:"missing_sidecars"`
	Existing       uint64 `json:"existing_sidecars"`
	Written        uint64 `json:"written_sidecars"`
	BALBytes       uint64 `json:"bal_bytes"`
	SourceSHA256   string `json:"source_record_digests_sha256"`
	DryRun         bool   `json:"dry_run"`
	CompletedAt    int64  `json:"completed_at_unix"`
}

type Record struct {
	Number     uint64            `json:"number"`
	Hash       string            `json:"hash"`
	StateRoot  string            `json:"state_root"`
	BALHash    string            `json:"bal_hash"`
	NewPayload []json.RawMessage `json:"new_payload"`
}

type Payload struct {
	Number    string `json:"blockNumber"`
	Hash      string `json:"blockHash"`
	StateRoot string `json:"stateRoot"`
	BAL       string `json:"blockAccessList"`
}

type decodedRecord struct {
	record Record
	bal    []byte
	digest [32]byte
	err    error
}

// Only decoding runs concurrently. The caller owns all database access and
// consumes results in block order, retaining at most one 128-record batch.
func decodeBatch(ctx context.Context, dir string, first, last uint64, workers int) ([]decodedRecord, error) {
	if first == 0 || last < first || last-first >= 128 || workers < 1 || workers > 4 {
		return nil, fmt.Errorf("invalid decoding batch")
	}
	results := make([]decodedRecord, last-first+1)
	var pending sync.WaitGroup
	for worker := 0; worker < min(workers, len(results)); worker++ {
		pending.Add(1)
		go func(index int) {
			defer pending.Done()
			for i := index; i < len(results); i += workers {
				if err := ctx.Err(); err != nil {
					results[i].err = err
					continue
				}
				r, _, bal, digest, err := load(dir, first+uint64(i))
				// The canonical checks need metadata and BAL bytes, not the raw
				// payload JSON retained by the decoder.
				r.NewPayload = nil
				results[i] = decodedRecord{r, bal, digest, err}
			}
		}(worker)
	}
	pending.Wait()
	for i := range results {
		if results[i].err != nil {
			return nil, fmt.Errorf("decode block %d: %w", first+uint64(i), results[i].err)
		}
	}
	return results, nil
}

func batchReader(ctx context.Context, dir string, end uint64) func(uint64) (Record, []byte, [32]byte, error) {
	var first uint64
	var batch []decodedRecord
	return func(n uint64) (Record, []byte, [32]byte, error) {
		if len(batch) == 0 || n < first || n-first >= uint64(len(batch)) {
			// Release the previous batch before allocating the next one.
			batch = nil
			var err error
			batch, err = decodeBatch(ctx, dir, n, min(end, n+127), 4)
			if err != nil {
				return Record{}, nil, [32]byte{}, err
			}
			first = n
		}
		item := batch[n-first]
		return item.record, item.bal, item.digest, nil
	}
}

func hash(s string) (common.Hash, error) {
	var h common.Hash
	if len(s) != 66 || !strings.HasPrefix(s, "0x") {
		return h, fmt.Errorf("invalid 32-byte hash")
	}
	b, err := hex.DecodeString(s[2:])
	if err != nil {
		return h, err
	}
	copy(h[:], b)
	return h, nil
}

func load(dir string, n uint64) (Record, Payload, []byte, [32]byte, error) {
	var r Record
	var p Payload
	var digest [32]byte
	path := filepath.Join(dir, fmt.Sprintf("%08d.json.gz", n))
	info, err := os.Stat(path)
	if err != nil {
		return r, p, nil, digest, err
	}
	if info.Size() > 32*1024*1024 {
		return r, p, nil, digest, fmt.Errorf("oversized record %d", n)
	}
	compressed, err := os.ReadFile(path)
	if err != nil {
		return r, p, nil, digest, err
	}
	digest = sha256.Sum256(compressed)
	z, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		return r, p, nil, digest, err
	}
	data, err := io.ReadAll(io.LimitReader(z, 16*1024*1024+1))
	z.Close()
	if err != nil {
		return r, p, nil, digest, err
	}
	if len(data) > 16*1024*1024 {
		return r, p, nil, digest, fmt.Errorf("oversized decoded record %d", n)
	}
	if err := json.Unmarshal(data, &r); err != nil {
		return r, p, nil, digest, err
	}
	if r.Number != n || len(r.NewPayload) == 0 {
		return r, p, nil, digest, fmt.Errorf("record number/payload mismatch at %d", n)
	}
	if err := json.Unmarshal(r.NewPayload[0], &p); err != nil {
		return r, p, nil, digest, err
	}
	pn, err := strconv.ParseUint(strings.TrimPrefix(p.Number, "0x"), 16, 64)
	if err != nil || pn != n || p.Hash != r.Hash || p.StateRoot != r.StateRoot {
		return r, p, nil, digest, fmt.Errorf("payload metadata mismatch at %d", n)
	}
	if !strings.HasPrefix(p.BAL, "0x") {
		return r, p, nil, digest, fmt.Errorf("missing BAL at %d", n)
	}
	bal, err := hex.DecodeString(p.BAL[2:])
	if err != nil {
		return r, p, nil, digest, err
	}
	if len(bal) == 0 {
		return r, p, nil, digest, fmt.Errorf("empty BAL encoding at %d", n)
	}
	return r, p, bal, digest, nil
}

func check(tx kv.Tx, r Record, bal []byte) (bool, error) {
	h, err := hash(r.Hash)
	if err != nil {
		return false, err
	}
	canonical, err := rawdb.ReadCanonicalHash(tx, r.Number)
	if err != nil {
		return false, err
	}
	if canonical != h {
		return false, fmt.Errorf("noncanonical record %d", r.Number)
	}
	header := rawdb.ReadHeader(tx, h, r.Number)
	if header == nil || header.Hash() != h || header.BlockAccessListHash == nil {
		return false, fmt.Errorf("missing native BAL header %d", r.Number)
	}
	root, err := hash(r.StateRoot)
	if err != nil {
		return false, err
	}
	commitment, err := hash(r.BALHash)
	if err != nil {
		return false, err
	}
	if header.Root != root || *header.BlockAccessListHash != commitment || crypto.Keccak256Hash(bal) != commitment {
		return false, fmt.Errorf("canonical state/BAL commitment mismatch at %d", r.Number)
	}
	prior, err := rawdb.ReadBlockAccessListBytes(tx, h, r.Number)
	if err != nil {
		return false, err
	}
	if len(prior) > 0 && !bytes.Equal(prior, bal) {
		return false, fmt.Errorf("conflicting stored BAL at %d", r.Number)
	}
	return len(prior) > 0, nil
}

func backfill(ctx context.Context, db kv.RwDB, dir string, start, end uint64, dry bool) (Report, error) {
	r := Report{Version: 1, ClientRevision: revision, Start: start, End: end, DryRun: dry}
	if start == 0 || end < start || end-start > 60000 {
		return r, fmt.Errorf("invalid bounded range")
	}
	digests := make([][32]byte, end-start+1)
	source := sha256.New()
	read := batchReader(ctx, dir, end)
	// Validate the entire input before the first write. A dry run may inspect an
	// older prefix of a live node through one consistent, read-only MDBX view.
	err := db.View(ctx, func(tx kv.Tx) error {
		h := rawdb.ReadHeadBlockHash(tx)
		number := rawdb.ReadHeaderNumber(tx, h)
		if number == nil || (!dry && *number != end) || (dry && *number < end) {
			return fmt.Errorf("native head does not match requested range")
		}
		header := rawdb.ReadHeader(tx, h, *number)
		if header == nil || rawdb.ReadForkchoiceHead(tx) != h {
			return fmt.Errorf("native head/forkchoice mismatch")
		}
		r.Head = *number
		r.HeadHash = h.Hex()
		r.StateRoot = header.Root.Hex()
		for n := start; n <= end; n++ {
			record, bal, digest, err := read(n)
			if err != nil {
				return err
			}
			existing, err := check(tx, record, bal)
			if err != nil {
				return err
			}
			digests[n-start] = digest
			source.Write(digest[:])
			r.Verified++
			r.BALBytes += uint64(len(bal))
			if existing {
				r.Existing++
			} else {
				r.Missing++
			}
			if r.Verified%1008 == 0 {
				fmt.Fprintf(os.Stderr, "BAL inputs verified: %d/%d\n", r.Verified, end-start+1)
			}
		}
		return nil
	})
	if err != nil {
		return r, err
	}
	r.SourceSHA256 = hex.EncodeToString(source.Sum(nil))
	if !dry {
		// A fresh reader is mandatory: the write pass must re-read every file
		// and compare its digest with the complete preflight, even for short runs.
		read = batchReader(ctx, dir, end)
		for first := start; first <= end; first += 128 {
			last := min(end, first+127)
			written := uint64(0)
			err := db.Update(ctx, func(tx kv.RwTx) error {
				for n := first; n <= last; n++ {
					record, bal, digest, err := read(n)
					if err != nil {
						return err
					}
					if digest != digests[n-start] {
						return fmt.Errorf("record changed after preflight at %d", n)
					}
					existing, err := check(tx, record, bal)
					if err != nil {
						return err
					}
					if existing {
						continue
					}
					h, _ := hash(record.Hash)
					if err := rawdb.WriteBlockAccessListBytes(tx, h, n, bal); err != nil {
						return err
					}
					written++
				}
				return nil
			})
			if err != nil {
				return r, err
			}
			r.Written += written
			fmt.Fprintf(os.Stderr, "Native BAL sidecars restored: %d/%d\n", r.Written, r.Missing)
		}
		if r.Written != r.Missing {
			return r, fmt.Errorf("write count mismatch")
		}
		if err := db.View(ctx, func(tx kv.Tx) error {
			h := rawdb.ReadHeadBlockHash(tx)
			header := rawdb.ReadHeader(tx, h, end)
			if header == nil || h.Hex() != r.HeadHash || header.Root.Hex() != r.StateRoot || rawdb.ReadForkchoiceHead(tx) != h {
				return fmt.Errorf("native head changed during backfill")
			}
			return nil
		}); err != nil {
			return r, err
		}
	}
	r.CompletedAt = time.Now().Unix()
	return r, nil
}

func run() error {
	dbPath := flag.String("db", "", "existing native chaindata directory")
	records := flag.String("records", "", "immutable gzip replay records")
	start := flag.Uint64("start", 0, "first generated block")
	end := flag.Uint64("end", 0, "final block; must equal native head for writes")
	reportPath := flag.String("report", "", "atomic JSON evidence destination")
	dry := flag.Bool("dry-run", false, "read-only preflight; permits an older prefix on a live node")
	flag.Parse()
	if *dbPath == "" || *records == "" || *reportPath == "" {
		return fmt.Errorf("db, records and report are required")
	}
	info, err := os.Stat(*dbPath)
	if err != nil || !info.IsDir() {
		return fmt.Errorf("database directory does not exist")
	}
	dataFile, err := os.Stat(filepath.Join(*dbPath, "mdbx.dat"))
	if err != nil || !dataFile.Mode().IsRegular() || dataFile.Size() == 0 {
		return fmt.Errorf("existing native mdbx.dat is required")
	}
	opts := mdbx.New(dbcfg.ChainDB, log.New()).Path(*dbPath).Accede(true).Readonly(*dry).Exclusive(!*dry)
	db, err := opts.Open(context.Background())
	if err != nil {
		return err
	}
	defer db.Close()
	r, err := backfill(context.Background(), db, *records, *start, *end, *dry)
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	file, err := os.OpenFile(*reportPath+".tmp", os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	if _, err := file.Write(data); err != nil {
		file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := os.Rename(*reportPath+".tmp", *reportPath); err != nil {
		return err
	}
	fmt.Print(string(data))
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
