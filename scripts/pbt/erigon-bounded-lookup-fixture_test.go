// Read-only lookup timing in a tiny temporary DB. Future file descriptors
// deliberately share the first file's backing data: the bounded lookup must
// skip all of them, so no extra disk dataset or production DB is needed.
package state

import (
	"bytes"
	"fmt"
	"testing"

	"github.com/erigontech/erigon/common/background"
	"github.com/erigontech/erigon/common/log/v3"
	"github.com/stretchr/testify/require"
)

func TestPBTBoundedLookupFutureFiles(t *testing.T) {
	db, d := testDbAndDomain(t, log.New())
	tx, err := db.BeginRw(t.Context())
	require.NoError(t, err)
	defer tx.Rollback()
	dt := d.beginForTests()
	w := dt.NewWriter(db)
	key, value := []byte("key"), []byte("at-step-zero")
	require.NoError(t, w.PutWithPrev(key, value, 5, nil))
	require.NoError(t, w.Flush(t.Context(), tx))
	w.Close()
	dt.Close()
	require.NoError(t, d.collateBuildIntegrate(t.Context(), 0, tx, background.NewProgressSet()))
	dt = d.beginForTests()
	original := dt.files
	defer func() { dt.files = original; dt.Close() }()
	require.Len(t, original, 1)
	for _, count := range []int{1, 219, 3068, 4096} {
		files := make(visibleFiles, count)
		files[0] = original[0]
		for i := 1; i < count; i++ {
			files[i] = original[0]
			files[i].startTxNum = uint64(i) * d.stepSize
			files[i].endTxNum = uint64(i+1) * d.stepSize
			files[i].i = i
		}
		for _, trimFuture := range []bool{false, true} {
			dt.files = files
			if trimFuture {
				dt.files = files[:1]
			}
			result := testing.Benchmark(func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					got, found, _, _, err := dt.getLatestFromFiles(key, nil, 0)
					if err != nil || !found || !bytes.Equal(got, value) {
						b.Fatalf("bounded lookup failed: %x %t %v", got, found, err)
					}
				}
			})
			t.Logf("files=%d trim_future=%t ns_per_lookup=%d allocations=%d runs=%d", count,
				trimFuture, result.NsPerOp(), result.AllocsPerOp(), result.N)
			fmt.Printf("PBT_LOOKUP files=%d trim_future=%t ns=%d\n", count, trimFuture, result.NsPerOp())
		}
	}
}
