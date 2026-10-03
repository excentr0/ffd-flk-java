import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/** Generic mechanisms only: callers must supply source-approved policy. */
public final class NestedChecks {
    private NestedChecks() {}

    /** Checks singleton occurrences inside ONE container; separate containers are independent. */
    public static <T> List<Integer> duplicateSingletonTags(List<T> occurrences, java.util.function.ToIntFunction<T> tag,
                                                            Set<Integer> singletonTags) {
        Map<Integer, Integer> counts = new HashMap<>();
        for (T occurrence : occurrences) {
            int t = tag.applyAsInt(occurrence);
            if (singletonTags.contains(t)) counts.merge(t, 1, Integer::sum);
        }
        return counts.entrySet().stream().filter(e -> e.getValue() > 1).map(Map.Entry::getKey).sorted().toList();
    }

    /** Inclusive exact decimal tolerance: true iff |actual-expected| <= tolerance. */
    public static boolean withinTolerance(BigDecimal actual, BigDecimal expected, BigDecimal tolerance) {
        Objects.requireNonNull(actual);
        Objects.requireNonNull(expected);
        Objects.requireNonNull(tolerance);
        if (tolerance.signum() < 0) throw new IllegalArgumentException("negative tolerance");
        return actual.subtract(expected).abs().compareTo(tolerance) <= 0;
    }

    /** Test occurrence carrier only; not a TLV decoder or a production fiscal model. */
    public record Field(int tag, Optional<String> value) {}

    public static void main(String[] args) {
        // Synthetic test policy: these numbers do NOT define any normative FFD rule.
        Set<Integer> singleton = Set.of(9001, 9002);
        var a = List.of(new Field(9001, Optional.of("x")), new Field(9001, Optional.of("y")), new Field(9003, Optional.empty()));
        var b = List.of(new Field(9001, Optional.of("z")));
        check(duplicateSingletonTags(a, Field::tag, singleton).equals(List.of(9001)), "duplicate in one container");
        check(duplicateSingletonTags(b, Field::tag, singleton).isEmpty(), "separate container unaffected");
        check(duplicateSingletonTags(List.<Field>of(), Field::tag, singleton).isEmpty(), "absent node");
        var states = List.of(new Field(9001, Optional.empty()), new Field(9001, Optional.of("")), new Field(9001, Optional.of("0")));
        check(duplicateSingletonTags(states, Field::tag, singleton).equals(List.of(9001)), "present null-model, empty and zero all count as occurrences");
        check(withinTolerance(new BigDecimal("10.01"), new BigDecimal("10"), new BigDecimal("0.01")), "inclusive edge");
        check(!withinTolerance(new BigDecimal("10.0101"), new BigDecimal("10"), new BigDecimal("0.01")), "just outside edge");
        check(withinTolerance(new BigDecimal("0.00"), new BigDecimal("0"), new BigDecimal("0")), "zero exact");
        check(!withinTolerance(new BigDecimal("0.0001"), new BigDecimal("0"), new BigDecimal("0")), "zero tolerance");
        System.out.println("PASS: nested duplicate and exact decimal boundary tests");
    }
    private static void check(boolean ok, String name) { if (!ok) throw new AssertionError(name); }
}
