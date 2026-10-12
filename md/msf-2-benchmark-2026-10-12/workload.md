# Captured benchmark workload

The [public RPC sample](evidence/workload-sample.json), captured from the bootnode at **22:42:26 UTC on October 12, 2026**, contains execution block **24455346**, hash `0x2a94c0503b084dc29ef6f80b00e80fe3c5a4d8e5100859ea2fb91c5e0def08f1`. The block uses **83,881,805 gas** out of a **200,000,000** limit. It has five transactions, each calling `0x2d03688a86865aef1c4bf7723c0712260e62ee39` with two 32-byte integer arguments.

The recipient has 122 bytes of code. The [disassembly](evidence/workload-disassembly.txt) shows a loop deriving addresses from `0xff`, deployer `0x4e59b44847b379578588920ca78fbf26c0b4956c`, a changing salt and the embedded init-code hash, then executing `CALL` with no input or output. The sampled argument ranges are:

| Transaction | Start salt | End salt | Loop iterations |
|---|---:|---:|---:|
| 0 | 16029 | 21371 | 5343 |
| 1 | 21372 | 26714 | 5343 |
| 2 | 26715 | 32057 | 5343 |
| 3 | 32058 | 37400 | 5343 |
| 4 | 37401 | 42743 | 5343 |

This is **26,715 target calls** across five ranges, inferred from the code and inputs, rather than measured by a live execution trace. The code pops each call result; receipt success alone would not prove every inner call succeeded.

For the first salt, Keccak-256 of the encoded CREATE2 address input yields callee `0xe4b6bd7dacd7c2319036aefd963b4acf8741d52e`. A separate [eth_getCode response at the same block](evidence/workload-callee-code.json) contains **65,536 bytes**. Its initial `PUSH2 0xffff; JUMP` transfers control to the final jump destination. One verified callee does not independently establish the size or successful execution of all 26,715 targets.

This sample gives client teams concrete code, input ranges and a state position for profiling. It was captured after the earlier Besu OOMs and is **not** identified as their exact triggering block. The Besu failure log separately records imports prefetching approximately 26,000 accounts, but that correlation does not prove which allocation exhausted the heap.

To build a controlled reproducer, restore the matching client snapshot and preserve the target code/state plus the captured raw transactions. Record CPU allocation, JVM sizing, client configuration and whether proposal construction runs concurrently with import. The captured public RPC block is an evidence attachment, not a portable standalone state fixture.
