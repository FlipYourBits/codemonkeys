<script lang="ts">
  let dragover = $state(false);

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragover = false;
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    dragover = true;
  }

  function handleDragLeave() {
    dragover = false;
  }
</script>

<div
  class="dropzone"
  class:dragover
  ondrop={handleDrop}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  role="region"
  aria-label="Drop files here"
>
  Drop files here
</div>

<style>
  .dropzone {
    padding: 16px;
    border: 2px dashed var(--border);
    border-radius: 8px;
    text-align: center;
    font-size: 12px;
    color: var(--text-dim);
    transition: border-color 0.15s, background 0.15s;
  }
  .dragover {
    border-color: var(--accent);
    background: rgba(129, 140, 248, 0.1);
    color: var(--accent);
  }
</style>
