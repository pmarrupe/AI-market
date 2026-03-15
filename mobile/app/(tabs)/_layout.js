import { Tabs } from "expo-router";

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarStyle: { backgroundColor: "#0f172a", borderTopColor: "#1e293b" },
        tabBarActiveTintColor: "#60a5fa",
        tabBarInactiveTintColor: "#64748b",
        headerStyle: { backgroundColor: "#0f172a" },
        headerTintColor: "#e2e8f0",
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "Dashboard", tabBarLabel: "Dashboard" }}
      />
      <Tabs.Screen
        name="scanner"
        options={{ title: "Scanner", tabBarLabel: "Scanner" }}
      />
      <Tabs.Screen
        name="trackers"
        options={{ title: "Trackers", tabBarLabel: "Trackers" }}
      />
      <Tabs.Screen
        name="research"
        options={{ title: "Research", tabBarLabel: "Research" }}
      />
      <Tabs.Screen
        name="search"
        options={{ title: "Search", tabBarLabel: "Search" }}
      />
    </Tabs>
  );
}
