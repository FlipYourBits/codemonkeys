<script lang="ts">
  import '../app.css';
</script>

<div class="dashboard">
  <header class="topbar">
    <div class="brand">
      <span class="logo">🐒</span>
      <span class="title">Codemonkeys</span>
    </div>
    <div class="session-cost">
      <span class="label">Session cost:</span>
      <span class="value">$0.00</span>
    </div>
  </header>
  <main class="panels">
    <aside class="file-picker">File Picker (TODO)</aside>
    <section class="agent-monitor">Agent Monitor (TODO)</section>
    <aside class="results-panel">Results Panel (TODO)</aside>
  </main>
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 2px solid var(--border);
    background: var(--bg-raised);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo { font-size: 18px; }
  .title { font-weight: 700; font-size: 16px; }

  .session-cost .label {
    font-size: 12px;
    color: var(--text-dim);
    margin-right: 8px;
  }

  .session-cost .value {
    font-size: 14px;
    font-weight: 600;
    color: var(--green);
  }

  .panels {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    flex: 1;
    overflow: hidden;
  }

  .file-picker {
    border-right: 1px solid var(--border);
    padding: 16px;
    overflow-y: auto;
  }

  .agent-monitor {
    overflow-y: auto;
    padding: 16px;
  }

  .results-panel {
    border-left: 1px solid var(--border);
    overflow-y: auto;
    padding: 16px;
  }
</style>
