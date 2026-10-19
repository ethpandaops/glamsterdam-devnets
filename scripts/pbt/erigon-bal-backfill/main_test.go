package main

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/c2h5oh/datasize"
	"github.com/erigontech/erigon/common"
	"github.com/erigontech/erigon/common/crypto"
	"github.com/erigontech/erigon/common/log/v3"
	"github.com/erigontech/erigon/db/kv"
	"github.com/erigontech/erigon/db/kv/dbcfg"
	"github.com/erigontech/erigon/db/kv/mdbx"
	"github.com/erigontech/erigon/db/rawdb"
	"github.com/erigontech/erigon/execution/types"
	"github.com/holiman/uint256"
)

func fixture(t *testing.T) (kv.RwDB, string, []*types.Header) {
	t.Helper()
	db, err := mdbx.New(dbcfg.ChainDB, log.New()).Path(t.TempDir()).MapSize(128 * datasize.MB).GrowthStep(16 * datasize.MB).Open(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(db.Close)
	dir := t.TempDir()
	var headers []*types.Header
	for n := uint64(1); n <= 2; n++ {
		zero := common.Hash{}
		u := uint64(0)
		balHash := crypto.Keccak256Hash([]byte{0xc0})
		h := &types.Header{Root: common.HexToHash("0x1234"), Number: *uint256.NewInt(n), GasLimit: 200000000,
			BaseFee: uint256.NewInt(1), WithdrawalsHash: &zero, BlobGasUsed: &u, ExcessBlobGas: &u,
			ParentBeaconBlockRoot: &zero, RequestsHash: &zero, BlockAccessListHash: &balHash, SlotNumber: &u}
		if n > 1 {
			h.ParentHash = headers[len(headers)-1].Hash()
		}
		headers = append(headers, h)
		if err := db.Update(context.Background(), func(tx kv.RwTx) error {
			if err := rawdb.WriteHeader(tx, h); err != nil {
				return err
			}
			if err := rawdb.WriteCanonicalHash(tx, h.Hash(), n); err != nil {
				return err
			}
			rawdb.WriteHeadBlockHash(tx, h.Hash())
			hash := h.Hash()
			return tx.Put(kv.LastForkchoice, []byte("headBlockHash"), hash[:])
		}); err != nil {
			t.Fatal(err)
		}
		writeRecord(t, dir, h, "0xc0")
	}
	return db, dir, headers
}

func writeRecord(t *testing.T, dir string, h *types.Header, bal string) {
	t.Helper()
	r := map[string]any{"number": h.Number.Uint64(), "hash": h.Hash().Hex(), "state_root": h.Root.Hex(), "bal_hash": h.BlockAccessListHash.Hex(),
		"new_payload": []any{map[string]any{"blockNumber": fmt.Sprintf("0x%x", h.Number.Uint64()), "blockHash": h.Hash().Hex(), "stateRoot": h.Root.Hex(), "blockAccessList": bal}}}
	f, err := os.Create(filepath.Join(dir, fmt.Sprintf("%08d.json.gz", h.Number.Uint64())))
	if err != nil {
		t.Fatal(err)
	}
	z := gzip.NewWriter(f)
	if err := json.NewEncoder(z).Encode(r); err != nil {
		t.Fatal(err)
	}
	if err := z.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}

func stored(t *testing.T, db kv.RwDB, h *types.Header) []byte {
	t.Helper()
	var out []byte
	if err := db.View(context.Background(), func(tx kv.Tx) error {
		b, err := rawdb.ReadBlockAccessListBytes(tx, h.Hash(), h.Number.Uint64())
		out = append([]byte(nil), b...)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	return out
}

func TestRestoreAndIdempotence(t *testing.T) {
	db, dir, headers := fixture(t)
	r, err := backfill(context.Background(), db, dir, 1, 2, false)
	if err != nil {
		t.Fatal(err)
	}
	if r.Written != 2 || r.Existing != 0 {
		t.Fatalf("unexpected report: %+v", r)
	}
	for _, h := range headers {
		if got := stored(t, db, h); string(got) != string([]byte{0xc0}) {
			t.Fatalf("missing native BAL: %x", got)
		}
	}
	r, err = backfill(context.Background(), db, dir, 1, 2, false)
	if err != nil || r.Written != 0 || r.Existing != 2 {
		t.Fatalf("not idempotent: %+v %v", r, err)
	}
}

func TestRejectCorruptionBeforeAnyWrite(t *testing.T) {
	db, dir, headers := fixture(t)
	writeRecord(t, dir, headers[1], "0xc101")
	if _, err := backfill(context.Background(), db, dir, 1, 2, false); err == nil {
		t.Fatal("accepted a BAL differing from canonical commitment")
	}
	for _, h := range headers {
		if len(stored(t, db, h)) != 0 {
			t.Fatal("wrote data before full validation")
		}
	}
}

func TestRejectConflictingNativeSidecar(t *testing.T) {
	db, dir, headers := fixture(t)
	if err := db.Update(context.Background(), func(tx kv.RwTx) error {
		return rawdb.WriteBlockAccessListBytes(tx, headers[1].Hash(), 2, []byte{0xc1, 1})
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := backfill(context.Background(), db, dir, 1, 2, false); err == nil {
		t.Fatal("overwrote a conflicting native sidecar")
	}
	if len(stored(t, db, headers[0])) != 0 {
		t.Fatal("partially wrote before conflict")
	}
}

func TestDryRunAndWrongHead(t *testing.T) {
	db, dir, headers := fixture(t)
	r, err := backfill(context.Background(), db, dir, 1, 2, true)
	if err != nil || r.Written != 0 || r.Missing != 2 {
		t.Fatalf("dry-run: %+v %v", r, err)
	}
	if len(stored(t, db, headers[0])) != 0 {
		t.Fatal("dry-run wrote data")
	}
	if _, err := backfill(context.Background(), db, dir, 1, 1, false); err == nil {
		t.Fatal("accepted wrong native head")
	}
}

func TestRejectNoncanonicalRecord(t *testing.T) {
	db, dir, headers := fixture(t)
	if err := db.Update(context.Background(), func(tx kv.RwTx) error { return rawdb.WriteCanonicalHash(tx, common.Hash{}, 2) }); err != nil {
		t.Fatal(err)
	}
	if _, err := backfill(context.Background(), db, dir, 1, 2, false); err == nil {
		t.Fatal("accepted a noncanonical record")
	}
	if len(stored(t, db, headers[0])) != 0 {
		t.Fatal("partially wrote before canonical check")
	}
}

func TestNativeReopenPreservesSidecars(t *testing.T) {
	db, dir, headers := fixture(t)
	if _, err := backfill(context.Background(), db, dir, 1, 2, false); err != nil {
		t.Fatal(err)
	}
	path := db.(interface{ Path() string }).Path()
	db.Close()
	reopened, err := mdbx.New(dbcfg.ChainDB, log.New()).Path(path).Accede(true).Exclusive(true).Open(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(reopened.Close)
	r, err := backfill(context.Background(), reopened, dir, 1, 2, false)
	if err != nil || r.Existing != 2 || r.Written != 0 {
		t.Fatalf("native reopen: %+v %v", r, err)
	}
	for _, h := range headers {
		if got := stored(t, reopened, h); string(got) != string([]byte{0xc0}) {
			t.Fatalf("sidecar lost on reopen: %x", got)
		}
	}
}
