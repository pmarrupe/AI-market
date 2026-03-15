import { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { getSP500Opinion } from "../../api";

export default function OpinionScreen() {
  const { ticker } = useLocalSearchParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!ticker) return;
      try {
        const res = await getSP500Opinion(ticker);
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [ticker]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#60a5fa" />
        <Text style={styles.muted}>Loading opinion…</Text>
      </View>
    );
  }

  if (error || data?.error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{data?.error || error}</Text>
      </View>
    );
  }

  const up = data.day_change > 0;
  const down = data.day_change < 0;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.ticker}>{data.ticker}</Text>
        <Text style={styles.name}>{data.name}</Text>
        <View style={styles.badges}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{data.sector}</Text>
          </View>
          {data.signal && (
            <View style={[styles.badge, styles.badgeSignal]}>
              <Text style={styles.badgeText}>{data.signal}</Text>
            </View>
          )}
        </View>
      </View>

      {data.price > 0 && (
        <View style={styles.priceRow}>
          <Text style={styles.price}>${data.price?.toFixed(2)}</Text>
          <Text style={[styles.change, up && styles.changeUp, down && styles.changeDown]}>
            {data.day_change > 0 ? "+" : ""}{(data.day_change * 100).toFixed(2)}%
          </Text>
          {data.momentum != null && (
            <Text style={styles.momentum}>
              5D: {(data.momentum * 100).toFixed(2)}%
            </Text>
          )}
        </View>
      )}

      <View style={styles.metrics}>
        <Metric label="Score" value={data.score?.toFixed(3)} />
        <Metric label="Sentiment" value={data.sentiment?.toFixed(3)} />
        <Metric label="Confidence" value={data.confidence?.toFixed(3)} />
        {data.relevance > 0 && <Metric label="Relevance" value={data.relevance?.toFixed(3)} />}
        {data.liquidity != null && <Metric label="Liquidity" value={data.liquidity?.toFixed(3)} />}
      </View>

      <Text style={styles.thesis}>{data.thesis}</Text>

      {data.uncertainties?.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Uncertainties</Text>
          {data.uncertainties.map((u, i) => (
            <Text key={i} style={styles.bullet}>• {u}</Text>
          ))}
        </View>
      )}

      {data.headlines?.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Linked headlines</Text>
          {data.headlines.map((h, i) => (
            <Text key={i} style={styles.bullet}>• {h}</Text>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

function Metric({ label, value }) {
  return (
    <View style={metricStyles.wrap}>
      <Text style={metricStyles.label}>{label}</Text>
      <Text style={metricStyles.value}>{value}</Text>
    </View>
  );
}

const metricStyles = StyleSheet.create({
  wrap: { marginRight: 16, marginBottom: 8 },
  label: { fontSize: 10, color: "#64748b", textTransform: "uppercase", marginBottom: 2 },
  value: { fontSize: 16, fontWeight: "700", color: "#f1f5f9" },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#020617" },
  content: { padding: 16, paddingBottom: 32 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  muted: { marginTop: 8, color: "#64748b" },
  error: { color: "#f87171", textAlign: "center" },
  header: { marginBottom: 16 },
  ticker: { fontSize: 24, fontWeight: "800", color: "#f1f5f9" },
  name: { fontSize: 14, color: "#94a3b8", marginTop: 4 },
  badges: { flexDirection: "row", gap: 8, marginTop: 8, flexWrap: "wrap" },
  badge: {
    backgroundColor: "rgba(59,130,246,0.15)",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  badgeSignal: { backgroundColor: "rgba(16,185,129,0.15)" },
  badgeText: { fontSize: 11, fontWeight: "600", color: "#94a3b8" },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 16 },
  price: { fontSize: 26, fontWeight: "700", color: "#f1f5f9" },
  change: { fontSize: 14, fontWeight: "600" },
  changeUp: { color: "#34d399" },
  changeDown: { color: "#f87171" },
  momentum: { fontSize: 12, color: "#64748b" },
  metrics: { flexDirection: "row", flexWrap: "wrap", marginBottom: 16 },
  thesis: { fontSize: 14, color: "#cbd5e1", lineHeight: 22, marginBottom: 20 },
  section: { marginBottom: 16 },
  sectionTitle: { fontSize: 11, fontWeight: "700", color: "#64748b", textTransform: "uppercase", marginBottom: 8 },
  bullet: { fontSize: 13, color: "#94a3b8", marginBottom: 4, lineHeight: 20 },
});
