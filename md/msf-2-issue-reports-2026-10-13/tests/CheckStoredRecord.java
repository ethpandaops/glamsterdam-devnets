import java.nio.file.*;
import java.util.*;
import org.apache.tuweni.bytes.Bytes;
import tech.pegasys.teku.spec.SpecFactory;
import tech.pegasys.teku.storage.api.StoredBlockMetadata;
import tech.pegasys.teku.spec.schemas.SchemaDefinitionsGloas;

class CheckStoredRecord {
  public static void main(String[] args) throws Exception {
    var spec = SpecFactory.create(args[0]);
    var block = spec.deserializeSignedBeaconBlock(Bytes.wrap(Files.readAllBytes(Path.of(args[1]))));
    var envelope = spec.deserializeSignedBlindedExecutionPayloadEnvelope(Bytes.wrap(Files.readAllBytes(Path.of(args[2]))));
    System.out.println("BEACON_SLOT=" + block.getSlot());
    System.out.println("BEACON_ROOT=" + block.getRoot());
    boolean reproduced = false;
    try {
      StoredBlockMetadata.extractGloasForkChoiceRebuildData(block, Optional.of(envelope));
    } catch (IllegalStateException e) {
      if (!e.getMessage().startsWith("Blinded execution payload envelope parent block hash")) throw e;
      System.out.println("REPRODUCED=" + e.getMessage());
      reproduced = true;
    }
    if (!reproduced) throw new AssertionError("Expected the saved-record mismatch");
    if (args.length > 3) {
      var canonical = SchemaDefinitionsGloas.required(spec.atSlot(block.getSlot()).getSchemaDefinitions())
          .getSignedExecutionPayloadEnvelopeSchema().sszDeserialize(Bytes.wrap(Files.readAllBytes(Path.of(args[3]))));
      var canonicalBlinded = canonical.blind(spec);
      var result = StoredBlockMetadata.extractGloasForkChoiceRebuildData(block, Optional.of(canonicalBlinded));
      System.out.println("CANONICAL_CONTROL=" + result.orElseThrow());
      if (!canonical.getBeaconBlockRoot().equals(block.getRoot())) throw new AssertionError("Control root differs");
    }
  }
}
