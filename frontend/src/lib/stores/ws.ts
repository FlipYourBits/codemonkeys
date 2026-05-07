import { writable } from 'svelte/store';
import type { AgentEvent } from '$lib/types';

export const connected = writable(false);
export const lastEvent = writable<AgentEvent | null>(null);

let socket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;

export function connect() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/ws`;

  socket = new WebSocket(url);

  socket.onopen = () => {
    connected.set(true);
    reconnectDelay = 1000;
  };

  socket.onmessage = (event) => {
    const data: AgentEvent = JSON.parse(event.data);
    lastEvent.set(data);
  };

  socket.onclose = () => {
    connected.set(false);
    socket = null;
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      connect();
    }, reconnectDelay);
  };

  socket.onerror = () => {
    socket?.close();
  };
}

export function disconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  socket?.close();
  socket = null;
}
