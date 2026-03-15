import { useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { searchSP500 } from "../../api";

export default function SearchScreen() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [debounceTimer, setDebounceTimer] = useState(null);
  const router = useRouter();

  const runSearch = useCallback(async (q) => {
    if (!q?.trim()) {
      setSuggestions([]);
      return;
    }
    setLoading(true);
    try {
      const results = await searchSP500(q.trim(), 10);
      setSuggestions(results);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = useCallback(
    (text) => {
      setQuery(text);
      if (debounceTimer) clearTimeout(debounceTimer);
      const t = setTimeout(() => runSearch(text), 280);
      setDebounceTimer(t);
    },
    [debounceTimer, runSearch]
  );

  const selectTicker = useCallback(
    (ticker) => {
      setSuggestions([]);
      setQuery("");
      router.push(`/opinion/${ticker}`);
    },
    [router]
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      <View style={styles.searchWrap}>
        <TextInput
          style={styles.input}
          placeholder="Search S&P 500 — ticker or company"
          placeholderTextColor="#64748b"
          value={query}
          onChangeText={handleChange}
          autoCapitalize="characters"
          autoCorrect={false}
        />
        {loading && (
          <ActivityIndicator size="small" color="#60a5fa" style={styles.loader} />
        )}
      </View>

      {suggestions.length > 0 && (
        <View style={styles.listWrap}>
          <FlatList
            data={suggestions}
            keyExtractor={(item) => item.ticker}
            keyboardShouldPersistTaps="handled"
            renderItem={({ item }) => (
              <TouchableOpacity
                style={styles.suggestionRow}
                onPress={() => selectTicker(item.ticker)}
                activeOpacity={0.7}
              >
                <Text style={styles.suggestionTicker}>{item.ticker}</Text>
                <Text style={styles.suggestionName} numberOfLines={1}>
                  {item.name}
                </Text>
                <Text style={styles.suggestionSector}>{item.sector}</Text>
              </TouchableOpacity>
            )}
          />
        </View>
      )}

      {query.trim().length > 0 && suggestions.length === 0 && !loading && (
        <Text style={styles.hint}>Type to search. Tap a result for AI opinion.</Text>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#020617", padding: 16 },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderWidth: 1,
    borderColor: "#1e293b",
    borderRadius: 12,
    paddingHorizontal: 14,
    marginBottom: 12,
  },
  input: {
    flex: 1,
    paddingVertical: 14,
    fontSize: 16,
    color: "#e2e8f0",
  },
  loader: { marginLeft: 8 },
  listWrap: {
    backgroundColor: "#0f172a",
    borderWidth: 1,
    borderColor: "#1e293b",
    borderRadius: 12,
    maxHeight: 360,
  },
  suggestionRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.04)",
    gap: 10,
  },
  suggestionTicker: { fontWeight: "700", color: "#60a5fa", width: 52 },
  suggestionName: { flex: 1, color: "#cbd5e1", fontSize: 14 },
  suggestionSector: { fontSize: 11, color: "#64748b" },
  hint: { fontSize: 13, color: "#64748b", marginTop: 12 },
});
