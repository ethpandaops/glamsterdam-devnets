package main

import (
	"encoding/json"
	"github.com/erigontech/mdbx-go/mdbx"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Opt-in disposable fixture for a real container PID namespace. The database
// is deliberately separate from the preparation datadir.
func TestDisposableContainerOwner(t *testing.T) {
	if os.Getenv("PBT_CONTAINER_OWNER") != "1" {
		t.Skip("container fixture only")
	}
	dir := os.Getenv("PBT_CONTAINER_FIXTURE")
	if !strings.HasPrefix(dir, "/fixture/") {
		t.Fatal("fixture mount path required")
	}
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	env, err := mdbx.NewEnv("pbt-container-fixture")
	if err != nil {
		t.Fatal(err)
	}
	if err = env.Open(dir, mdbx.SafeNoSync|mdbx.WriteMap, 0600); err != nil {
		t.Fatal(err)
	}
	defer env.Close()
	// Commit dirty data before holding the next writer transaction. Without
	// this, Env.Sync can return immediately without testing the shared lock.
	err = env.Update(func(tx *mdbx.Txn) error {
		dbi, e := tx.OpenRoot(0)
		if e != nil {
			return e
		}
		return tx.Put(dbi, []byte("fixture"), []byte("committed-dirty"), 0)
	})
	if err != nil {
		t.Fatal(err)
	}
	err = env.Update(func(tx *mdbx.Txn) error {
		dbi, e := tx.OpenRoot(0)
		if e != nil {
			return e
		}
		if e = tx.Put(dbi, []byte("fixture"), []byte("initial"), 0); e != nil {
			return e
		}
		if e = os.WriteFile(filepath.Join(filepath.Dir(dir), "ready"), []byte("ready"), 0600); e != nil {
			return e
		}
		// A contender must wait for this transaction across the process boundary.
		time.Sleep(15 * time.Second)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(120 * time.Second)
	for time.Now().Before(deadline) {
		if _, err = os.Stat(filepath.Join(filepath.Dir(dir), "stop")); err == nil {
			break
		}
		time.Sleep(time.Second)
	}
	period, err := env.GetSyncPeriod()
	if err != nil {
		t.Fatal(err)
	}
	threshold, err := env.GetSyncBytes()
	if err != nil {
		t.Fatal(err)
	}
	data, _ := json.Marshal(map[string]any{"period_seconds": period.Seconds(), "threshold_bytes": threshold})
	if err = os.WriteFile(filepath.Join(filepath.Dir(dir), "owner-result.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
}
