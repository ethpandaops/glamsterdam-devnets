import java.nio.file.*;
import java.util.*;
import org.rocksdb.*;
import org.apache.tuweni.bytes.Bytes;
import tech.pegasys.teku.spec.SpecFactory;

class InspectEnvelope {
  public static void main(String[] args) throws Exception {
    RocksDB.loadLibrary();
    var root = HexFormat.of().parseHex("3c681a001b2ec71bf23d98c8b1b963b756d53477cb9a4daa52f65c71f25c6549");
    var spec = SpecFactory.create(args[1]);
    var handles = new ArrayList<ColumnFamilyHandle>();
    try (var options = new Options(); var dbOptions = new DBOptions()) {
      var families = RocksDB.listColumnFamilies(options, args[0]);
      var descriptors = families.stream().map(ColumnFamilyDescriptor::new).toList();
      try (var db = RocksDB.openReadOnly(dbOptions, args[0], descriptors, handles)) {
        for (int i = 0; i < handles.size(); i++) {
          byte[] value = db.get(handles.get(i), root);
          if (value == null) continue;
          System.out.println("CF_HEX=" + HexFormat.of().formatHex(families.get(i)) + " VALUE_BYTES=" + value.length);
          if (families.get(i).length == 1 && families.get(i)[0] == 1) {
            Files.write(Path.of(args[2] + ".block.ssz"), value);
          }
          try {
            var envelope = spec.deserializeSignedBlindedExecutionPayloadEnvelope(Bytes.wrap(value));
            if (!Arrays.equals(envelope.getBeaconBlockRoot().toArray(), root)) continue;
            var h = envelope.getMessage().getPayloadHeader();
            System.out.println("ROOT=" + envelope.getBeaconBlockRoot());
            System.out.println("SLOT=" + envelope.getMessage().getSlot());
            System.out.println("PARENT_HASH=" + h.getParentHash());
            System.out.println("BLOCK_HASH=" + h.getBlockHash());
            System.out.println("BLOCK_NUMBER=" + h.getBlockNumber());
            System.out.println("GAS_LIMIT=" + h.getGasLimit());
            Files.write(Path.of(args[2]), value);
            System.out.println("EXTRACTED_BYTES=" + value.length);
          } catch (RuntimeException e) {
            System.out.println("OTHER_RECORD=" + e.getClass().getSimpleName());
          }
        }
      } finally { handles.forEach(ColumnFamilyHandle::close); }
    }
  }
}
