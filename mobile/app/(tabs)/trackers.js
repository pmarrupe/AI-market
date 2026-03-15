import { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Linking,
  RefreshControl,
} from "react-native";
import { fetchDashboard } from "../../api";
import { relativeTime } from "../../utils/relativeTime";

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

export default function TrackersScreen() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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

  const funding = data?.startup_funding ?? [];
  const launches = data?.product_launches ?? [];
  const [featuredFunding, ...restFunding] = funding;
  const [featuredLaunch, ...restLaunches] = launches;

  if (loading && !data) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#60a5fa" />
        <Text style={styles.muted}>Loading trackers…</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#60a5fa" />
      }
    >
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Startup & Funding</Text>
          <Text style={styles.badge}>{funding.length} events</Text>
        </View>
        {featuredFunding && (
          <TouchableOpacity
            style={styles.featured}
            onPress={() => featuredFunding.url && Linking.openURL(featuredFunding.url)}
            activeOpacity={0.8}
          >
            <Text style={styles.featuredTitle}>{featuredFunding.startup}</Text>
            <Text style={styles.featuredSub}>
              {featuredFunding.stage && `${featuredFunding.stage} · `}
              {featuredFunding.amount && featuredFunding.amount !== "Undisclosed" ? featuredFunding.amount : "Undisclosed"}
            </Text>
            <View style={styles.featuredMeta}>
              <Text style={styles.featuredSource}>{featuredFunding.source}</Text>
              <Text style={styles.featuredTime}>{relativeTime(featuredFunding.published_at)}</Text>
            </View>
          </TouchableOpacity>
        )}
        {restFunding.map((item, i) => (
          <TouchableOpacity
            key={i}
            style={styles.feedRow}
            onPress={() => item.url && Linking.openURL(item.url)}
            activeOpacity={0.8}
          >
            <Text style={styles.feedTitle}>{item.startup}</Text>
            <Text style={styles.feedSub}>{item.amount || item.stage || ""}</Text>
            <Text style={styles.feedMeta}>{item.source} · {relativeTime(item.published_at)}</Text>
          </TouchableOpacity>
        ))}
        {funding.length === 0 && <Text style={styles.empty}>No funding items yet.</Text>}
      </View>

      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Product Launches</Text>
          <Text style={styles.badge}>{launches.length} launches</Text>
        </View>
        {featuredLaunch && (
          <TouchableOpacity
            style={styles.featured}
            onPress={() => featuredLaunch.url && Linking.openURL(featuredLaunch.url)}
            activeOpacity={0.8}
          >
            <Text style={styles.featuredTitle}>{featuredLaunch.product}</Text>
            {featuredLaunch.company_hint && (
              <Text style={styles.featuredSub}>by {featuredLaunch.company_hint}</Text>
            )}
            <View style={styles.featuredMeta}>
              <Text style={styles.featuredSource}>{featuredLaunch.source}</Text>
              <Text style={styles.featuredTime}>{relativeTime(featuredLaunch.published_at)}</Text>
            </View>
          </TouchableOpacity>
        )}
        {restLaunches.map((item, i) => (
          <TouchableOpacity
            key={i}
            style={styles.feedRow}
            onPress={() => item.url && Linking.openURL(item.url)}
            activeOpacity={0.8}
          >
            <Text style={styles.feedTitle}>{item.product}</Text>
            {item.company_hint && <Text style={styles.feedSub}>{item.company_hint}</Text>}
            <Text style={styles.feedMeta}>{item.source} · {relativeTime(item.published_at)}</Text>
          </TouchableOpacity>
        ))}
        {launches.length === 0 && <Text style={styles.empty}>No launches yet.</Text>}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#020617" },
  content: { padding: 16, paddingBottom: 32 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  muted: { color: "#64748b" },
  section: { marginBottom: 28 },
  sectionHeader: { flexDirection: "row", alignItems: "center", marginBottom: 12, gap: 10 },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: "#e2e8f0" },
  badge: { fontSize: 11, color: "#64748b", backgroundColor: "rgba(59,130,246,0.15)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  featured: {
    backgroundColor: "rgba(59,130,246,0.08)",
    borderLeftWidth: 3,
    borderLeftColor: "rgba(59,130,246,0.7)",
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  featuredTitle: { fontSize: 16, fontWeight: "700", color: "#edf2ff", marginBottom: 4 },
  featuredSub: { fontSize: 13, color: "#94a3b8", marginBottom: 8 },
  featuredMeta: { flexDirection: "row", gap: 8 },
  featuredSource: { fontSize: 11, color: "#64748b" },
  featuredTime: { fontSize: 11, color: "#64748b" },
  feedRow: {
    padding: 14,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.04)",
    backgroundColor: "#0f172a",
    borderRadius: 8,
    marginBottom: 4,
  },
  feedTitle: { fontSize: 14, fontWeight: "500", color: "#cbd5e1", marginBottom: 2 },
  feedSub: { fontSize: 12, color: "#64748b", marginBottom: 4 },
  feedMeta: { fontSize: 11, color: "#475569" },
  empty: { fontSize: 13, color: "#64748b", fontStyle: "italic", padding: 12 },
});
