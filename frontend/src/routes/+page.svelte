<script lang="ts">
  import '../app.css';
  import { onMount, onDestroy } from 'svelte';
  import { connect, disconnect } from '$lib/stores/ws';
  import { fetchAgents } from '$lib/stores/agents';
  import TopBar from '$lib/components/TopBar.svelte';
  import FilePicker from '$lib/components/FilePicker.svelte';
  import AgentMonitor from '$lib/components/AgentMonitor.svelte';
  import ResultsPanel from '$lib/components/ResultsPanel.svelte';

  onMount(() => {
    connect();
    fetchAgents();
  });

  onDestroy(() => {
    disconnect();
  });
</script>

<div class="dashboard">
  <TopBar />
  <main class="panels">
    <aside class="file-picker">
      <FilePicker />
    </aside>
    <section class="agent-monitor">
      <AgentMonitor />
    </section>
    <aside class="results-panel">
      <ResultsPanel />
    </aside>
  </main>
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .panels {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    flex: 1;
    overflow: hidden;
  }
  .file-picker {
    border-right: 1px solid var(--border);
    overflow: hidden;
  }
  .agent-monitor { overflow: hidden; }
  .results-panel {
    border-left: 1px solid var(--border);
    overflow: hidden;
  }
</style>
