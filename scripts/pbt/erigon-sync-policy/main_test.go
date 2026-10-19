package main

import (
	"fmt"
	"github.com/erigontech/mdbx-go/mdbx"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func fixture(t *testing.T, flags uint) (*mdbx.Env, string) {
	t.Helper()
	path := t.TempDir()
	env, err := mdbx.NewEnv("pbt-policy-test")
	if err != nil {
		t.Fatal(err)
	}
	if err = env.Open(path, flags, 0600); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := env.Close(); err != nil {
			t.Error(err)
		}
	})
	return env, path
}

func TestCrossProcessSyncThresholds(t *testing.T) {
	env, path := fixture(t, mdbx.SafeNoSync|mdbx.WriteMap)
	cmd := exec.Command(os.Args[0], "-test.run=^TestHelperProcess$", path)
	cmd.Env = append(os.Environ(), "PBT_SYNC_HELPER=1")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("%v: %s", err, out)
	}
	period, err := env.GetSyncPeriod()
	if err != nil {
		t.Fatal(err)
	}
	size, err := env.GetSyncBytes()
	if err != nil {
		t.Fatal(err)
	}
	if period > 10*time.Second || 10*time.Second-period > 100*time.Microsecond || size != 256*1024*1024 {
		t.Fatalf("settings not shared: %s %d", period, size)
	}
}

func TestHelperProcess(t *testing.T) {
	if os.Getenv("PBT_SYNC_HELPER") != "1" {
		return
	}
	_, err := configure(os.Args[len(os.Args)-1], 10*time.Second, 256*1024*1024)
	if err != nil {
		t.Fatal(err)
	}
}

func TestRejectWrongModeWithoutChangingThresholds(t *testing.T) {
	for _, flags := range []uint{0, mdbx.UtterlyNoSync, mdbx.NoMetaSync} {
		t.Run(fmt.Sprintf("flags_%x", flags), func(t *testing.T) {
			env, path := fixture(t, flags)
			// Open/configure in another process; two handles to one DB in one process
			// are forbidden by MDBX, independently of the policy guard being tested.
			cmd := exec.Command(os.Args[0], "-test.run=^TestHelperProcess$", path)
			cmd.Env = append(os.Environ(), "PBT_SYNC_HELPER=1")
			if err := cmd.Run(); err == nil {
				t.Fatal("unexpected acceptance")
			}
			p, err := env.GetSyncPeriod()
			if err != nil {
				t.Fatal(err)
			}
			b, err := env.GetSyncBytes()
			if err != nil {
				t.Fatal(err)
			}
			if p != 0 || b != 0 {
				t.Fatalf("modified rejected database: %s %d", p, b)
			}
		})
	}
}

func TestRejectMissingDatabase(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing")
	if _, err := configure(path, 10*time.Second, 256*1024*1024); err == nil {
		t.Fatal("missing DB accepted")
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("created database path")
	}
}

func TestOwnerGuard(t *testing.T) {
	_, path := fixture(t, mdbx.SafeNoSync|mdbx.WriteMap)
	if err := verifyOwner(path, os.Getpid()); err != nil {
		t.Fatal(err)
	}
	if err := verifyOwner(path, 0); err == nil {
		t.Fatal("missing owner accepted")
	}
	unrelated := t.TempDir()
	if err := os.WriteFile(filepath.Join(unrelated, "mdbx.dat"), []byte("unrelated"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := verifyOwner(unrelated, os.Getpid()); err == nil {
		t.Fatal("unrelated database accepted")
	}
}
