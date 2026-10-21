// Inject into db/state as a Go build overlay; never alters the deployed binary.
package state_test

import (
	"context"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/erigontech/erigon/common/log/v3"
	"github.com/erigontech/erigon/db/kv"
	"github.com/erigontech/erigon/db/state"
	"github.com/erigontech/erigon/execution/commitment"
	v3 "github.com/erigontech/erigon/execution/commitment/v3"
	"github.com/stretchr/testify/require"
)

func TestPBTPreparationV3Continue(t *testing.T) {
	db, agg := testDbAggregatorWithFiles(t, &testAggConfig{stepSize: 10, disableCommitmentBranchTransform: true})
	tx, err := db.BeginTemporalRo(t.Context())
	require.NoError(t, err)
	legacy, found, _, _, err := state.AggTx(tx).DebugGetLatestFromFiles(kv.CommitmentDomain, commitment.KeyCommitmentState, math.MaxUint64)
	require.NoError(t, err)
	require.True(t, found)
	converted, err := v3.ConvertLegacyState(legacy)
	require.NoError(t, err)
	wantBlock, wantTx, wantRoot, err := commitment.DecodeCommitmentV3State(converted)
	require.NoError(t, err)
	tx.Rollback()

	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	state.SetConvertPhase1AfterFileHookForTest(func(idx int) {
		if idx == 0 {
			cancel()
		}
	})
	t.Cleanup(func() { state.SetConvertPhase1AfterFileHookForTest(nil) })
	rw, err := db.BeginTemporalRw(ctx)
	require.NoError(t, err)
	err = state.ConvertCommitmentFiles(ctx, state.AggTx(rw), state.ConvertOpts{TargetV3: true}, log.New())
	rw.Rollback()
	require.ErrorIs(t, err, context.Canceled)
	state.SetConvertPhase1AfterFileHookForTest(nil)
	files, err := filepath.Glob(filepath.Join(agg.Dirs().Snap, "rebuild", "domain", "v3.0-commitment.*.kv"))
	require.NoError(t, err)
	require.Len(t, files, 1)
	before, err := os.Stat(files[0])
	require.NoError(t, err)
	stem := strings.TrimSuffix(strings.TrimPrefix(filepath.Base(files[0]), "v3.0-"), ".kv")
	for _, ext := range []string{".bt", ".kvei"} {
		siblings, err := filepath.Glob(filepath.Join(filepath.Dir(files[0]), "*-"+stem+ext))
		require.NoError(t, err)
		require.Len(t, siblings, 1)
	}

	runOrchestrator(t, db, state.ConvertOpts{TargetV3: true, Continue: true})
	after, err := os.Stat(filepath.Join(agg.Dirs().SnapDomain, filepath.Base(files[0])))
	require.NoError(t, err)
	require.True(t, os.SameFile(before, after), "completed shard must be reused")
	tx, err = db.BeginTemporalRo(t.Context())
	require.NoError(t, err)
	defer tx.Rollback()
	value, _, err := tx.GetLatest(kv.CommitmentDomain, commitment.KeyCommitmentV3State, kv.GetLatestOptions{})
	require.NoError(t, err)
	block, txn, root, err := commitment.DecodeCommitmentV3State(value)
	require.NoError(t, err)
	require.Equal(t, wantBlock, block)
	require.Equal(t, wantTx, txn)
	require.Equal(t, wantRoot, root)
}
