// Read-only diagnostic, built against the pinned Erigon checkout. It compares
// every record in a merged accounts/storage file with the newest record from
// a contiguous set of retained fragments. It does not open or change a DB.
package main

import (
	"bytes"
	"container/heap"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"

	"github.com/erigontech/erigon/db/seg"
	"github.com/erigontech/erigon/db/state/statecfg"
)

type input struct {
	path       string
	from, to   uint64
	stat       os.FileInfo
	d          *seg.Decompressor
	r          *seg.Reader
	key, value []byte
	valid      bool
}

var nameRE = regexp.MustCompile(`^v[0-9.]+-(accounts|storage)\.([0-9]+)-([0-9]+)\.kv$`)

func open(path, domain string) (*input, error) {
	m := nameRE.FindStringSubmatch(filepath.Base(path))
	if m == nil || m[1] != domain {
		return nil, fmt.Errorf("unexpected file: %s", path)
	}
	from, err := strconv.ParseUint(m[2], 10, 64)
	if err != nil {
		return nil, err
	}
	to, err := strconv.ParseUint(m[3], 10, 64)
	if err != nil {
		return nil, err
	}
	if from >= to {
		return nil, fmt.Errorf("invalid range: %s", path)
	}
	s, err := os.Stat(path)
	if err != nil {
		return nil, err
	}
	d, err := seg.NewDecompressor(path)
	if err != nil {
		return nil, err
	}
	c := statecfg.Schema.AccountsDomain.Compression
	if domain == "storage" {
		c = statecfg.Schema.StorageDomain.Compression
	}
	x := &input{path: path, from: from, to: to, stat: s, d: d, r: seg.NewReader(d.MakeGetter(), c)}
	if err := x.next(); err != nil {
		d.Close()
		return nil, err
	}
	return x, nil
}

func (x *input) next() error {
	if !x.r.HasNext() {
		x.valid = false
		return nil
	}
	k, _ := x.r.Next(nil)
	if !x.r.HasNext() {
		return fmt.Errorf("missing value: %s", x.path)
	}
	v, _ := x.r.Next(nil)
	if x.valid && bytes.Compare(x.key, k) >= 0 {
		return fmt.Errorf("keys not strictly sorted: %s", x.path)
	}
	x.key, x.value, x.valid = bytes.Clone(k), bytes.Clone(v), true
	return nil
}

type inputs []*input

func (h inputs) Len() int           { return len(h) }
func (h inputs) Less(i, j int) bool { return bytes.Compare(h[i].key, h[j].key) < 0 }
func (h inputs) Swap(i, j int)      { h[i], h[j] = h[j], h[i] }
func (h *inputs) Push(v any)        { *h = append(*h, v.(*input)) }
func (h *inputs) Pop() any          { n := len(*h) - 1; v := (*h)[n]; *h = (*h)[:n]; return v }

func run() error {
	if len(os.Args) < 4 {
		return fmt.Errorf("usage: verify-domain-fragments accounts|storage MERGED FRAGMENT...")
	}
	domain := os.Args[1]
	if domain != "accounts" && domain != "storage" {
		return fmt.Errorf("unsupported domain")
	}
	merged, err := open(os.Args[2], domain)
	if err != nil {
		return err
	}
	defer merged.d.Close()
	all := []*input{merged}
	frags := []*input{}
	for _, p := range os.Args[3:] {
		f, e := open(p, domain)
		if e != nil {
			return e
		}
		defer f.d.Close()
		frags = append(frags, f)
		all = append(all, f)
	}
	sort.Slice(frags, func(i, j int) bool { return frags[i].from < frags[j].from })
	end := merged.from
	for _, f := range frags {
		if f.from != end || f.to > merged.to {
			return fmt.Errorf("gap, overlap or overflow at %s", f.path)
		}
		end = f.to
	}
	if end != merged.to {
		return fmt.Errorf("incomplete coverage")
	}
	h := inputs{}
	for _, f := range frags {
		if f.valid {
			heap.Push(&h, f)
		}
	}
	digest := sha256.New()
	var count uint64
	var size [8]byte
	for h.Len() > 0 {
		key := bytes.Clone(h[0].key)
		var value []byte
		var newest uint64
		for h.Len() > 0 && bytes.Equal(h[0].key, key) {
			f := heap.Pop(&h).(*input)
			if f.to > newest {
				newest = f.to
				value = bytes.Clone(f.value)
			}
			if err := f.next(); err != nil {
				return err
			}
			if f.valid {
				heap.Push(&h, f)
			}
		}
		if !merged.valid || !bytes.Equal(key, merged.key) || !bytes.Equal(value, merged.value) {
			return fmt.Errorf("merged record mismatch at key %x after %d records", key, count)
		}
		binary.BigEndian.PutUint64(size[:], uint64(len(key)))
		digest.Write(size[:])
		digest.Write(key)
		binary.BigEndian.PutUint64(size[:], uint64(len(value)))
		digest.Write(size[:])
		digest.Write(value)
		count++
		if count%10000000 == 0 {
			fmt.Fprintf(os.Stderr, "verified %d records\n", count)
		}
		if err := merged.next(); err != nil {
			return err
		}
	}
	if merged.valid {
		return fmt.Errorf("extra records in merged file")
	}
	for _, f := range all {
		s, e := os.Stat(f.path)
		if e != nil {
			return e
		}
		if !os.SameFile(s, f.stat) || s.Size() != f.stat.Size() || !s.ModTime().Equal(f.stat.ModTime()) {
			return fmt.Errorf("input changed during read: %s", f.path)
		}
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"domain": domain, "merged": merged.path, "fragments": len(frags), "records": count, "logical_sha256": hex.EncodeToString(digest.Sum(nil)), "all_records_equal": true, "inputs_unchanged": true})
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
