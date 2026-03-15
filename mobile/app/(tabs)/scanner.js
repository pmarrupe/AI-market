import { useEffect, useState, useMemo, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
} from "react-native";
import { useRouter } from "expo-router";
import { fetchDashboard, refreshIntelligence } from "../../api";

const SORT_OPTIONS = [
  { value: "rank_asc", label: "Best opportunities" },
  { value: "confidence_desc", label: "Highest confidence" },
  { value: "momentum_desc", label: "Strongest momentum" },
  { value: "delta_desc", label: "Biggest Δ score" },
];

function getSortKey(sortValue) {
  const map = {
    rank: "opportunityRank",
    confidence: "confidence",
    momentum: "momentum",
    delta: "score_delta",
  };
  return map[sortValue] || "opportunityRank";
}

export default function ScannerScreen() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filterModal, setFilterModal] = useState(false);
  const [sortModal, setSortModal] = useState(false);
  const [filters, setFilters] = useState({ sector: "", signal: "", risk: "" });
  const [sortBy, setSortBy] = useState("rank_asc");
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchDashboard();
      setData(res);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshIntelligence();
      await load();
    } catch {
      setRefreshing(false);
    }
  }, [load]);

  const rows = data?.stock_rows ?? [];
  const filtered = useMemo(() => {
    let result = rows.filter(
      (r) =>
        (!filters.sector || r.sector === filters.sector) &&
        (!filters.signal || r.signalLabel === filters.signal) &&
        (!filters.risk || r.riskLevel === filters.risk)
    );
    const [metric, direction] = sortBy.split("_");
    const key = getSortKey(metric);
    result.sort((a, b) => {
      const aVal = a[key] ?? -999;
      const bVal = b[key] ?? -999;
      return direction === "asc" ? aVal - bVal : bVal - aVal;
    });
    return result;
  }, [rows, filters, sortBy]);

  const sortLabel = SORT_OPTIONS.find((o) => o.value === sortBy)?.label ?? "Sort";
  const hasFilters = filters.sector || filters.signal || filters.risk;

  const toggleExpand = (ticker) => {
    setExpanded((p) => (p === ticker ? null : ticker));
  };

  if (loading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#60a5fa" />
        <Text style={styles.muted}>Loading scanner…</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.toolbar}>
        <TouchableOpacity style={styles.toolbarBtn} onPress={() => setSortModal(true)}>
          <Text style={styles.toolbarBtnText}>{sortLabel}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.toolbarBtn, hasFilters && styles.toolbarBtnActive]}
          onPress={() => setFilterModal(true)}
        >
          <Text style={styles.toolbarBtnText}>Filter</Text>
        </TouchableOpacity>
        <Text style={styles.toolbarCount}>{filtered.length} of {rows.length}</Text>
      </View>

      {rows.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.muted}>No stock scores yet. Pull to refresh.</Text>
          <TouchableOpacity style={styles.button} onPress={onRefresh}>
            <Text style={styles.buttonText}>Refresh</Text>
          </TouchableOpacity>
        </View>
      ) : filtered.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.muted}>No matches. Clear filters.</Text>
          <TouchableOpacity
            style={styles.button}
            onPress={() => setFilters({ sector: "", signal: "", risk: "" })}
          >
            <Text style={styles.buttonText}>Clear filters</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => item.ticker}
          contentContainerStyle={styles.listContent}
          refreshing={refreshing}
          onRefresh={onRefresh}
          renderItem={({ item }) => (
            <View style={styles.rowWrap}>
              <TouchableOpacity
                style={styles.row}
                onPress={() => toggleExpand(item.ticker)}
                activeOpacity={0.7}
              >
                <Text style={styles.rowTicker}>{item.ticker}</Text>
                <Text style={styles.rowSector}>{item.sector}</Text>
                <Text style={styles.rowScore}>{item.score?.toFixed(3)}</Text>
                <View style={[styles.pill, item.signalColor === "green" && styles.pillGreen]}>
                  <Text style={styles.pillText}>{item.signalLabel}</Text>
                </View>
                <Text style={styles.chevron}>{expanded === item.ticker ? "▼" : "▶"}</Text>
              </TouchableOpacity>
              {expanded === item.ticker && (
                <View style={styles.detail}>
                  <Text style={styles.detailText}>
                    {item.company} · {item.riskLevel} risk · {item.timeHorizon}
                  </Text>
                  <Text style={styles.detailSummary} numberOfLines={3}>{item.aiSummary}</Text>
                  <TouchableOpacity onPress={() => router.push(`/opinion/${item.ticker}`)}>
                    <Text style={styles.detailLink}>View full opinion →</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}
        />
      )}

      <Modal visible={sortModal} transparent animationType="fade">
        <Pressable style={styles.modalBackdrop} onPress={() => setSortModal(false)}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>Sort by</Text>
            {SORT_OPTIONS.map((opt) => (
              <TouchableOpacity
                key={opt.value}
                style={styles.modalOption}
                onPress={() => {
                  setSortBy(opt.value);
                  setSortModal(false);
                }}
              >
                <Text style={styles.modalOptionText}>{opt.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      </Modal>

      <Modal visible={filterModal} transparent animationType="fade">
        <Pressable style={styles.modalBackdrop} onPress={() => setFilterModal(false)}>
          <ScrollView contentContainerStyle={styles.modalScroll}>
            <View style={styles.modalBox}>
              <Text style={styles.modalTitle}>Sector</Text>
              <View style={styles.chipRow}>
                <TouchableOpacity
                  style={[styles.chip, !filters.sector && styles.chipActive]}
                  onPress={() => setFilters((f) => ({ ...f, sector: "" }))}
                >
                  <Text style={styles.chipText}>All</Text>
                </TouchableOpacity>
                {(data?.stock_sectors ?? []).map((s) => (
                  <TouchableOpacity
                    key={s}
                    style={[styles.chip, filters.sector === s && styles.chipActive]}
                    onPress={() => setFilters((f) => ({ ...f, sector: s }))}
                  >
                    <Text style={styles.chipText}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.modalTitle}>Signal</Text>
              <View style={styles.chipRow}>
                <TouchableOpacity
                  style={[styles.chip, !filters.signal && styles.chipActive]}
                  onPress={() => setFilters((f) => ({ ...f, signal: "" }))}
                >
                  <Text style={styles.chipText}>All</Text>
                </TouchableOpacity>
                {(data?.stock_signal_labels ?? []).map((s) => (
                  <TouchableOpacity
                    key={s}
                    style={[styles.chip, filters.signal === s && styles.chipActive]}
                    onPress={() => setFilters((f) => ({ ...f, signal: s }))}
                  >
                    <Text style={styles.chipText}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.modalTitle}>Risk</Text>
              <View style={styles.chipRow}>
                <TouchableOpacity
                  style={[styles.chip, !filters.risk && styles.chipActive]}
                  onPress={() => setFilters((f) => ({ ...f, risk: "" }))}
                >
                  <Text style={styles.chipText}>All</Text>
                </TouchableOpacity>
                {(data?.stock_risk_levels ?? []).map((r) => (
                  <TouchableOpacity
                    key={r}
                    style={[styles.chip, filters.risk === r && styles.chipActive]}
                    onPress={() => setFilters((f) => ({ ...f, risk: r }))}
                  >
                    <Text style={styles.chipText}>{r}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity style={styles.modalDone} onPress={() => setFilterModal(false)}>
                <Text style={styles.modalDoneText}>Done</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#020617" },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  muted: { color: "#64748b", marginBottom: 12 },
  button: { backgroundColor: "rgba(59,130,246,0.2)", paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10 },
  buttonText: { color: "#60a5fa", fontWeight: "600" },
  toolbar: { flexDirection: "row", alignItems: "center", padding: 12, gap: 8, borderBottomWidth: 1, borderBottomColor: "#1e293b" },
  toolbarBtn: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: "#0f172a", borderWidth: 1, borderColor: "#1e293b" },
  toolbarBtnActive: { borderColor: "#60a5fa" },
  toolbarBtnText: { color: "#e2e8f0", fontSize: 13, fontWeight: "600" },
  toolbarCount: { marginLeft: "auto", fontSize: 12, color: "#64748b" },
  listContent: { padding: 12, paddingBottom: 32 },
  rowWrap: { marginBottom: 4 },
  row: { flexDirection: "row", alignItems: "center", padding: 12, backgroundColor: "#0f172a", borderRadius: 10, borderWidth: 1, borderColor: "#1e293b", gap: 8 },
  rowTicker: { fontWeight: "700", color: "#e2e8f0", width: 48 },
  rowSector: { flex: 1, fontSize: 12, color: "#64748b", numberOfLines: 1 },
  rowScore: { color: "#94a3b8", fontVariant: ["tabular-nums"], width: 44 },
  pill: { backgroundColor: "rgba(148,163,184,0.2)", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999 },
  pillGreen: { backgroundColor: "rgba(16,185,129,0.2)" },
  pillText: { fontSize: 10, fontWeight: "600", color: "#94a3b8" },
  chevron: { color: "#64748b", fontSize: 10 },
  detail: { padding: 12, paddingTop: 4, paddingLeft: 20, backgroundColor: "rgba(15,23,42,0.8)", borderLeftWidth: 3, borderLeftColor: "rgba(59,130,246,0.5)", marginLeft: 12, marginTop: -8, marginBottom: 8, borderRadius: 0, borderBottomLeftRadius: 10, borderBottomRightRadius: 10 },
  detailText: { fontSize: 12, color: "#94a3b8", marginBottom: 6 },
  detailSummary: { fontSize: 12, color: "#cbd5e1", marginBottom: 8 },
  detailLink: { fontSize: 12, color: "#60a5fa", fontWeight: "600" },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", alignItems: "center", padding: 24 },
  modalScroll: { flexGrow: 1, justifyContent: "center" },
  modalBox: { backgroundColor: "#0f172a", borderRadius: 16, padding: 20, width: "100%", maxWidth: 400 },
  modalTitle: { fontSize: 11, fontWeight: "700", color: "#64748b", textTransform: "uppercase", marginBottom: 8, marginTop: 12 },
  modalOption: { paddingVertical: 12 },
  modalOptionText: { color: "#e2e8f0", fontSize: 16 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.05)", borderWidth: 1, borderColor: "#1e293b" },
  chipActive: { borderColor: "#60a5fa", backgroundColor: "rgba(59,130,246,0.15)" },
  chipText: { color: "#e2e8f0", fontSize: 13 },
  modalDone: { marginTop: 20, padding: 14, alignItems: "center", backgroundColor: "rgba(59,130,246,0.2)", borderRadius: 10 },
  modalDoneText: { color: "#60a5fa", fontWeight: "700" },
});
