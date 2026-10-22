package state

import (
	"testing"

	"github.com/erigontech/erigon/common/background"
	"github.com/erigontech/erigon/common/log/v3"
	"github.com/erigontech/erigon/db/kv"
	"github.com/stretchr/testify/require"
)

func TestPBTBoundedViewPreservesSplitRejection(t *testing.T) {
	dt := &DomainRoTx{name: kv.AccountsDomain, stepSize: 16, files: visibleFiles{
		{startTxNum: 0, endTxNum: 32}, {startTxNum: 32, endTxNum: 48},
	}}
	limitLegacyConversionFiles(dt, 0)
	require.Len(t, dt.files, 1)
	_, found, _, _, err := dt.getLatestFromFiles([]byte("key"), nil, 0)
	require.ErrorContains(t, err, "max step 0 splits accounts domain file")
	require.False(t, found)
}

func TestPBTBoundedViewOnlyDropsTrailingFutureFiles(t *testing.T) {
	dt := &DomainRoTx{stepSize: 16, files: visibleFiles{
		{startTxNum: 0, endTxNum: 16}, {startTxNum: 48, endTxNum: 64},
		{startTxNum: 16, endTxNum: 32}, {startTxNum: 64, endTxNum: 80},
	}}
	limitLegacyConversionFiles(dt, 1)
	require.Len(t, dt.files, 3)
	// Even unexpected nonmonotonic starts cannot discard an eligible file or
	// change any original file index. Extra middle entries are simply retained.
	require.Equal(t, uint64(48), dt.files[1].startTxNum)
	require.Equal(t, uint64(16), dt.files[2].startTxNum)
}

func TestPBTBoundedViewEmptyAndUnbounded(t *testing.T) {
	dt := &DomainRoTx{stepSize: 16, files: visibleFiles{{startTxNum: 16, endTxNum: 32}}}
	limitLegacyConversionFiles(dt, kv.NoStepBound)
	require.Len(t, dt.files, 1)
	limitLegacyConversionFiles(dt, 0)
	require.NotNil(t, dt.files, "retain non-nil slice so normal close cleanup still runs")
	require.Empty(t, dt.files)
	_, found, _, _, err := dt.getLatestFromFiles([]byte("key"), nil, 0)
	require.NoError(t, err)
	require.False(t, found)
}

func TestPBTBoundedViewDoesNotChangeSharedGeneration(t *testing.T) {
	db, d := testDbAndDomain(t, log.New())
	tx, err := db.BeginRw(t.Context())
	require.NoError(t, err)
	defer tx.Rollback()
	dt := d.beginForTests()
	w := dt.NewWriter(db)
	key, first, second := []byte("key"), []byte("first"), []byte("second")
	require.NoError(t, w.PutWithPrev(key, first, 5, nil))
	require.NoError(t, w.PutWithPrev(key, second, 20, first))
	require.NoError(t, w.Flush(t.Context(), tx))
	w.Close()
	dt.Close()
	for step := kv.Step(0); step < 2; step++ {
		require.NoError(t, d.collateBuildIntegrate(t.Context(), step, tx, background.NewProgressSet()))
	}
	dt = d.beginForTests()
	require.Len(t, dt.files, 2)
	limitLegacyConversionFiles(dt, 0)
	require.Len(t, dt.files, 1)
	require.Len(t, dt.visible.files, 2)
	got, found, _, _, err := dt.getLatestFromFiles(key, nil, 0)
	require.NoError(t, err)
	require.True(t, found)
	require.Equal(t, first, got)
	dt.Close()
	fresh := d.beginForTests()
	defer fresh.Close()
	require.Len(t, fresh.files, 2)
	got, found, _, _, err = fresh.getLatestFromFiles(key, nil, 1)
	require.NoError(t, err)
	require.True(t, found)
	require.Equal(t, second, got)
}
