// Run through overlays against both original and candidate converter source.
// Compare all PBT_RECORD_DIGEST lines; these hash decompressed records, not
// compression output or indexes, which may have nondeterministic encoding.
package state_test

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"path/filepath"
	"testing"

	"github.com/erigontech/erigon/db/state"
	"github.com/stretchr/testify/require"
)

func TestPBTConversionRecordEquivalence(t *testing.T) {
	db, agg := testDbAggregatorWithFiles(t, &testAggConfig{stepSize: 10, disableCommitmentBranchTransform: true})
	runOrchestrator(t, db, state.ConvertOpts{TargetV3: true})
	paths, err := filepath.Glob(filepath.Join(agg.Dirs().SnapDomain, "v3.0-commitment.*.kv"))
	require.NoError(t, err)
	require.Greater(t, len(paths), 1, "exercise initial and incremental conversion")
	for _, path := range paths {
		keys, vals := readKVFile(t, agg, path)
		require.NotEmpty(t, keys)
		h := sha256.New()
		var size [8]byte
		for i, key := range keys {
			for _, item := range [][]byte{key, vals[i]} {
				binary.BigEndian.PutUint64(size[:], uint64(len(item)))
				h.Write(size[:])
				h.Write(item)
			}
		}
		fmt.Printf("PBT_RECORD_DIGEST %s records=%d sha256=%x\n", filepath.Base(path), len(keys), h.Sum(nil))
	}
}
