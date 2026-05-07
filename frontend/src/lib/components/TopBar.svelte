<script lang="ts">
  import { sessionCost } from '$lib/stores/runs';

  function formatCost(cost: number): string {
    return `$${cost.toFixed(cost < 0.01 ? 4 : 2)}`;
  }
</script>

<header class="topbar">
  <div class="brand">
    <span class="logo">🐒</span>
    <span class="title">Codemonkeys</span>
  </div>
  <div class="session-cost">
    <span class="label">Session cost:</span>
    <span class="value">{formatCost($sessionCost)}</span>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 2px solid var(--border);
    background: var(--bg-raised);
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .logo { font-size: 18px; }
  .title { font-weight: 700; font-size: 16px; }
  .label { font-size: 12px; color: var(--text-dim); margin-right: 8px; }
  .value { font-size: 14px; font-weight: 600; color: var(--green); }
</style>
