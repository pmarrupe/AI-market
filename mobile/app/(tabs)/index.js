import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
  TouchableOpacity,
} from "react-native";
import { useRouter } from "expo-router";
import { fetchDashboard, refreshIntelligence } from "../../api";

function formatFundingTotal(items) {
  if (!items || items.length === 0) return "$0";
  let totalM = 0;
  for (const item of items) {
    const raw = (item.amount || "").toUpperCase();
    const match = raw.match(/([\d.]+)\s*(B|BILLION|M|MILLION)/);
    if (!match) continue;
    const num = parseFloat(match[1]);
    const unit = match[2];
    if (unit.startsWith("B")) totalM += num * 1000;
    else totalM += num;
  }
  if (totalM >= 1000) return `$${(totalM / 1000).toFixed(1)}B`;
  if (totalM > 0) return `$${Math.round(totalM)}M`;
  return `${items.length}`;
}

export default function DashboardScreen() {
  const router = useRouter();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const res = await fetchDashboard();
      setData(res);
    } catch (e) {
      setError(e.message);
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

  if (loading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#60a5fa" />
        <Text style={styles.muted}>Loading dashboard…</Text>
      </View>
    );
  }

  if (error && !data) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{error}</Text>
        <TouchableOpacity style={styles.button} onPress={load}>
          <Text style={styles.buttonText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const kpis = [
    { label: "Stocks tracked", value: data?.stocks?.length ?? 0 },
    { label: "Funding events", value: data?.startup_funding?.length ?? 0 },
    { label: "Product launches", value: data?.product_launches?.length ?? 0 },
    { label: "Research items", value: data?.research_items?.length ?? 0 },
  ];

  const summaryFunding = formatFundingTotal(data?.startup_funding ?? []);
  const topSectorName = (data?.industry_map?.[0]?.sector) ?? "—";

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor="#60a5fa"
        />
      }
    >
      <Text style={styles.eyebrow}>AI Market Command Center</Text>

      <View style={styles.summaryBar}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Funding</Text>
          <Text style={[styles.summaryValue, styles.summaryGreen]}>{summaryFunding}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Launches</Text>
          <Text style={styles.summaryValue}>{data?.product_launches?.length ?? 0}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Top sector</Text>
          <Text style={styles.summaryValue} numberOfLines={1}>{topSectorName}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Research</Text>
          <Text style={styles.summaryValue}>{data?.research_items?.length ?? 0}</Text>
        </View>
      </View>

      <View style={styles.disclaimer}>
        <Text style={styles.disclaimerText}>
          Research intelligence only. Not personalized investment advice.
        </Text>
      </View>

      <View style={styles.kpiGrid}>
        {kpis.map((item) => (
          <View key={item.label} style={styles.kpiCard}>
            <Text style={styles.kpiLabel}>{item.label}</Text>
            <Text style={styles.kpiValue}>{item.value}</Text>
          </View>
        ))}
      </View>

      {data?.stock_rows?.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Top opportunities</Text>
          {data.stock_rows.slice(0, 5).map((row) => (
            <TouchableOpacity
              key={row.ticker}
              style={styles.row}
              onPress={() => router.push(`/opinion/${row.ticker}`)}
              activeOpacity={0.7}
            >
              <Text style={styles.rowTicker}>{row.ticker}</Text>
              <Text style={styles.rowScore}>{row.score?.toFixed(3)}</Text>
              <View style={[styles.pill, row.signalColor === "green" && styles.pillGreen]}>
                <Text style={styles.pillText}>{row.signalLabel}</Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {data?.industry_map?.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Sectors</Text>
          {data.industry_map.slice(0, 5).map((s) => (
            <Text key={s.sector} style={styles.muted}>
              {s.sector} — {s.tickers?.length ?? 0} tickers
            </Text>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#020617" },
  content: { padding: 16, paddingBottom: 32 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  eyebrow: {
    fontSize: 12,
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 8,
  },
  summaryBar: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 12,
  },
  summaryCard: {
    flex: 1,
    minWidth: "47%",
    backgroundColor: "#0f172a",
    borderWidth: 1,
    borderColor: "#1e293b",
    borderRadius: 10,
    padding: 10,
  },
  summaryLabel: { fontSize: 10, color: "#64748b", textTransform: "uppercase", marginBottom: 2 },
  summaryValue: { fontSize: 14, fontWeight: "700", color: "#f1f5f9" },
  summaryGreen: { color: "#34d399" },
  disclaimer: {
    backgroundColor: "rgba(124,92,255,0.08)",
    borderWidth: 1,
    borderColor: "rgba(124,92,255,0.2)",
    borderRadius: 10,
    padding: 10,
    marginBottom: 16,
  },
  disclaimerText: { fontSize: 12, color: "#94a3b8" },
  kpiGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginBottom: 24,
  },
  kpiCard: {
    flex: 1,
    minWidth: "45%",
    backgroundColor: "#0f172a",
    borderWidth: 1,
    borderColor: "#1e293b",
    borderRadius: 12,
    padding: 14,
  },
  kpiLabel: { fontSize: 11, color: "#64748b", textTransform: "uppercase", marginBottom: 4 },
  kpiValue: { fontSize: 24, fontWeight: "800", color: "#f1f5f9" },
  section: { marginBottom: 24 },
  sectionTitle: { fontSize: 16, fontWeight: "700", color: "#e2e8f0", marginBottom: 10 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.06)",
    gap: 12,
  },
  rowTicker: { fontWeight: "700", color: "#e2e8f0", width: 56 },
  rowScore: { color: "#94a3b8", fontVariant: ["tabular-nums"], flex: 1 },
  pill: {
    backgroundColor: "rgba(148,163,184,0.2)",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
  },
  pillGreen: { backgroundColor: "rgba(16,185,129,0.2)" },
  pillText: { fontSize: 11, fontWeight: "600", color: "#94a3b8" },
  muted: { fontSize: 13, color: "#64748b", marginBottom: 4 },
  error: { color: "#f87171", marginBottom: 12, textAlign: "center" },
  button: {
    backgroundColor: "rgba(59,130,246,0.2)",
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
  },
  buttonText: { color: "#60a5fa", fontWeight: "600" },
});
