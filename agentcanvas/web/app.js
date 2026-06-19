(function () {
  "use strict";

  const VIEW_DEFS = [
    {
      id: "current",
      label: "Current Change",
      summary: "Focus on the active edit surface and nearby dependencies.",
    },
    {
      id: "repo",
      label: "Repo Wide",
      summary: "Scan high-level components and zoom into layers for detail.",
    },
    {
      id: "routes",
      label: "Routes",
      summary: "Inspect handoffs, edges, API flows, and reroute candidates.",
    },
    {
      id: "tests",
      label: "Tests",
      summary: "Find covered and uncovered test paths before asking an agent to change code.",
    },
  ];

  const REQUEST_DEFS = {
    add_note: {
      title: "Add note",
      tone: "neutral",
      fields: [
        { id: "note", label: "Note", type: "textarea", required: true },
      ],
    },
    add_node: {
      title: "Add node",
      tone: "neutral",
      fields: [
        { id: "label", label: "Node label", type: "text", required: true },
        { id: "node_type", label: "Node type", type: "text", value: "task" },
        { id: "reason", label: "Why this node belongs here", type: "textarea" },
      ],
    },
    remove_node: {
      title: "Remove node request",
      tone: "danger",
      fields: [
        { id: "reason", label: "Reason", type: "textarea", required: true },
      ],
    },
    reroute_edge: {
      title: "Re-route edge request",
      tone: "danger",
      fields: [
        { id: "from_node", label: "From node", type: "text" },
        { id: "to_node", label: "To node", type: "text" },
        { id: "note", label: "Routing note", type: "textarea", required: true },
      ],
    },
    change_node_flow: {
      title: "Change node flow",
      tone: "neutral",
      fields: [
        { id: "desired_flow", label: "Desired flow", type: "textarea", required: true },
      ],
    },
    request_test_coverage: {
      title: "Request test coverage",
      tone: "warning",
      fields: [
        { id: "coverage_target", label: "Coverage target", type: "text" },
        { id: "note", label: "Test note", type: "textarea", required: true },
      ],
    },
  };

  const FALLBACK_GRAPH = {
    metadata: {
      workspace: "Unindexed workspace",
      generated_at: new Date().toISOString(),
      revision: "fallback",
    },
    nodes: [
      {
        id: "workspace-index",
        label: "Workspace index",
        type: "source",
        confidence: 0.84,
        group: "Index",
        outputs: ["workflow-ir", "repo-layers"],
        source_refs: [{ path: ".agentcanvas/workflow.ir.json" }],
        notes: ["Fallback graph shown until /api/graph returns indexed data."],
      },
      {
        id: "workflow-ir",
        label: "Workflow IR",
        type: "graph",
        confidence: 0.78,
        group: "Index",
        inputs: ["workspace-index"],
        outputs: ["canvas-ui", "pending-requests"],
        source_refs: [{ path: ".agentcanvas/workflow.ir.json" }],
      },
      {
        id: "repo-layers",
        label: "Repo layers",
        type: "layer",
        confidence: 0.66,
        group: "Index",
        inputs: ["workspace-index"],
        outputs: ["canvas-ui"],
        source_refs: [{ path: "agentcanvas/indexer.py" }],
      },
      {
        id: "canvas-ui",
        label: "Browser canvas UI",
        type: "ui",
        confidence: 0.9,
        group: "Web UI",
        inputs: ["workflow-ir", "repo-layers"],
        outputs: ["pending-requests"],
        source_refs: [
          { path: "agentcanvas/web/index.html" },
          { path: "agentcanvas/web/app.js" },
          { path: "agentcanvas/web/styles.css" },
        ],
        notes: ["Operators queue requests here; coding agents implement from pending files."],
      },
      {
        id: "pending-requests",
        label: "Pending change requests",
        type: "queue",
        confidence: 0.72,
        group: "Agent Handoff",
        inputs: ["canvas-ui"],
        outputs: ["coding-agent"],
        source_refs: [{ path: ".agentcanvas/pending/" }],
      },
      {
        id: "coding-agent",
        label: "Coding agent handoff",
        type: "agent",
        confidence: 0.58,
        group: "Agent Handoff",
        inputs: ["pending-requests"],
        outputs: ["tests"],
        notes: ["Any coding agent can consume the queued Markdown and JSON requests."],
      },
      {
        id: "tests",
        label: "Test coverage requests",
        type: "test",
        confidence: 0.52,
        group: "Validation",
        inputs: ["coding-agent"],
        source_refs: [{ path: "tests/" }],
      },
    ],
    edges: [
      { id: "e1", source: "workspace-index", target: "workflow-ir", label: "writes" },
      { id: "e2", source: "workspace-index", target: "repo-layers", label: "derives" },
      { id: "e3", source: "workflow-ir", target: "canvas-ui", label: "serves" },
      { id: "e4", source: "repo-layers", target: "canvas-ui", label: "groups" },
      { id: "e5", source: "canvas-ui", target: "pending-requests", label: "queues" },
      { id: "e6", source: "pending-requests", target: "coding-agent", label: "hands off" },
      { id: "e7", source: "coding-agent", target: "tests", label: "verifies" },
    ],
  };

  const state = {
    activeView: "current",
    graphRaw: null,
    graphMeta: {},
    nodes: [],
    edges: [],
    groups: [],
    pending: [],
    selectedNodeId: null,
    selectedGroupId: null,
    zoom: 1,
    visibleNodes: [],
    visibleEdges: [],
    layout: new Map(),
    apiStatus: {
      graph: "loading",
      pending: "loading",
    },
  };

  const els = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    cacheElements();
    bindEvents();
    renderViewTabs();
    updateTokenStatus();
    loadAll();
  }

  function cacheElements() {
    els.workspaceLabel = document.getElementById("workspaceLabel");
    els.graphStatus = document.getElementById("graphStatus");
    els.tokenStatus = document.getElementById("tokenStatus");
    els.refreshButton = document.getElementById("refreshButton");
    els.reindexButton = document.getElementById("reindexButton");
    els.viewList = document.getElementById("viewList");
    els.layerList = document.getElementById("layerList");
    els.clearGroupButton = document.getElementById("clearGroupButton");
    els.viewTitle = document.getElementById("viewTitle");
    els.viewSummary = document.getElementById("viewSummary");
    els.canvasViewport = document.getElementById("canvasViewport");
    els.canvasContent = document.getElementById("canvasContent");
    els.edgeLayer = document.getElementById("edgeLayer");
    els.nodeLayer = document.getElementById("nodeLayer");
    els.zoomOutButton = document.getElementById("zoomOutButton");
    els.zoomFitButton = document.getElementById("zoomFitButton");
    els.zoomInButton = document.getElementById("zoomInButton");
    els.addNoteButton = document.getElementById("addNoteButton");
    els.addNodeButton = document.getElementById("addNodeButton");
    els.inspector = document.getElementById("inspector");
    els.pendingList = document.getElementById("pendingList");
    els.queueSummary = document.getElementById("queueSummary");
    els.refreshPendingButton = document.getElementById("refreshPendingButton");
    els.requestDialog = document.getElementById("requestDialog");
    els.requestForm = document.getElementById("requestForm");
    els.requestTitle = document.getElementById("requestTitle");
    els.requestTarget = document.getElementById("requestTarget");
    els.requestFields = document.getElementById("requestFields");
    els.submitRequestButton = document.getElementById("submitRequestButton");
  }

  function bindEvents() {
    els.refreshButton.addEventListener("click", loadAll);
    els.refreshPendingButton.addEventListener("click", loadPending);
    els.reindexButton.addEventListener("click", handleReindex);
    els.clearGroupButton.addEventListener("click", () => {
      state.selectedGroupId = null;
      state.selectedNodeId = null;
      render();
    });

    els.zoomOutButton.addEventListener("click", () => setZoom(state.zoom - 0.15));
    els.zoomInButton.addEventListener("click", () => setZoom(state.zoom + 0.15));
    els.zoomFitButton.addEventListener("click", () => {
      state.selectedGroupId = null;
      setZoom(1);
    });

    els.addNoteButton.addEventListener("click", () => openRequestDialog("add_note"));
    els.addNodeButton.addEventListener("click", () => openRequestDialog("add_node"));

    els.requestForm.addEventListener("submit", handleRequestSubmit);
    els.canvasViewport.addEventListener("click", (event) => {
      if (event.target === els.canvasViewport || event.target === els.canvasContent) {
        state.selectedNodeId = null;
        renderInspector();
        renderCanvasSelection();
      }
    });
  }

  async function loadAll() {
    setGraphStatus("Loading graph and pending queue", "loading");
    await Promise.all([loadGraph(), loadPending()]);
    render();
  }

  async function loadGraph() {
    try {
      const graph = await fetchJson("/api/graph");
      applyGraph(graph);
      state.apiStatus.graph = "live";
      setGraphStatus("Graph loaded from /api/graph", "live");
    } catch (error) {
      applyGraph(FALLBACK_GRAPH);
      state.apiStatus.graph = "fallback";
      setGraphStatus("Using fallback graph until /api/graph responds", "warning");
    }
  }

  async function loadPending() {
    try {
      const pending = await fetchJson("/api/pending");
      state.pending = normalizePending(pending);
      state.apiStatus.pending = "live";
    } catch (error) {
      state.pending = state.pending.filter((item) => item.localOnly);
      state.apiStatus.pending = "fallback";
    }
    renderPending();
  }

  async function handleReindex() {
    els.reindexButton.disabled = true;
    setGraphStatus("Reindex requested", "loading");
    try {
      await fetchJson("/api/reindex", { method: "POST", body: JSON.stringify({ source: "agentcanvas-web" }) });
      await loadGraph();
    } catch (error) {
      setGraphStatus("Reindex endpoint unavailable", "warning");
    } finally {
      els.reindexButton.disabled = false;
      render();
    }
  }

  function applyGraph(graph) {
    state.graphRaw = graph || FALLBACK_GRAPH;
    const normalized = normalizeGraph(state.graphRaw);
    state.graphMeta = normalized.meta;
    state.nodes = normalized.nodes;
    state.edges = normalized.edges;
    state.groups = normalized.groups;

    if (!state.selectedNodeId || !state.nodes.some((node) => node.id === state.selectedNodeId)) {
      state.selectedNodeId = state.nodes[0] ? state.nodes[0].id : null;
    }
  }

  function apiUrl(path) {
    const url = new URL(path, window.location.origin);
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      url.searchParams.set("token", token);
    }
    return url.toString();
  }

  async function fetchJson(path, options) {
    const response = await fetch(apiUrl(path), {
      headers: { "content-type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    if (response.status === 204) {
      return null;
    }
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }

  function normalizeGraph(raw) {
    const graph = raw && (raw.graph || raw.workflow || raw.ir || raw);
    const metadata = (raw && raw.metadata) || (graph && graph.metadata) || {};
    const meta = {
      workspace: pick(raw, ["workspace", "workspace_path"]) || pick(graph, ["workspace", "workspace_path"]) || pick(metadata, ["workspace", "workspace_path"]) || "Local workspace",
      generated_at: pick(raw, ["generated_at", "generatedAt"]) || pick(graph, ["generated_at", "generatedAt"]) || pick(metadata, ["generated_at", "generatedAt"]),
      revision: pick(raw, ["revision", "version"]) || pick(graph, ["revision", "version"]) || pick(metadata, ["revision", "version"]),
    };

    const rawNodes = coerceCollection(pick(graph, ["nodes", "vertices", "items"]));
    const nodes = rawNodes.map((node, index) => normalizeNode(node, index));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const rawEdges = coerceCollection(pick(graph, ["edges", "links", "routes"]));
    let edges = rawEdges
      .map((edge, index) => normalizeEdge(edge, index))
      .filter((edge) => edge.source && edge.target);

    if (!edges.length) {
      edges = inferEdgesFromNodeOutputs(nodes, nodeIds);
    }

    const rawGroups = coerceCollection(pick(graph, ["groups", "layers", "components"]));
    const groups = normalizeGroups(rawGroups, nodes);
    return { meta, nodes, edges, groups };
  }

  function normalizeNode(node, index) {
    const id = String(node.id || node.key || node.path || node.file || `node-${index + 1}`);
    const sources = normalizeRefs(
      node.source_refs || node.sourceRefs || node.sources || node.refs || node.files || node.paths || node.path || node.file
    );
    const label = String(node.label || node.name || node.title || lastPathSegment(sources[0] && sources[0].path) || id);
    const type = String(node.type || node.kind || node.role || inferType(label, sources));
    const group = String(node.group || node.layer || node.component || node.module || inferGroup(type, sources));
    const confidenceValue = Number(node.confidence ?? node.score ?? node.weight);
    return {
      raw: node,
      id,
      label,
      type,
      group,
      confidence: Number.isFinite(confidenceValue) ? clamp(confidenceValue, 0, 1) : null,
      sourceRefs: sources,
      inputs: asStringArray(node.inputs || node.inbound || node.dependencies || node.deps || node.consumes),
      outputs: asStringArray(node.outputs || node.outbound || node.provides || node.routes || node.next),
      notes: asStringArray(node.notes || node.annotations || node.comments || node.description),
      current: Boolean(node.current || node.active || node.in_current_change),
      testLike: isTestLike(type, label, sources),
      routeLike: isRouteLike(type, label, sources),
    };
  }

  function normalizeEdge(edge, index) {
    const pair = Array.isArray(edge.nodes) ? edge.nodes : [];
    const source = edge.source || edge.from || edge.input || pair[0];
    const target = edge.target || edge.to || edge.output || pair[1];
    return {
      raw: edge,
      id: String(edge.id || edge.key || `edge-${index + 1}`),
      source: source ? String(source) : "",
      target: target ? String(target) : "",
      label: String(edge.label || edge.name || edge.type || edge.kind || ""),
      type: String(edge.type || edge.kind || "flow"),
      confidence: Number.isFinite(Number(edge.confidence)) ? clamp(Number(edge.confidence), 0, 1) : null,
    };
  }

  function inferEdgesFromNodeOutputs(nodes, nodeIds) {
    const labelToId = new Map(nodes.map((node) => [node.label.toLowerCase(), node.id]));
    const edges = [];
    nodes.forEach((node) => {
      node.outputs.forEach((output, outputIndex) => {
        const target = nodeIds.has(output) ? output : labelToId.get(String(output).toLowerCase());
        if (target) {
          edges.push({
            id: `inferred-${node.id}-${outputIndex}`,
            source: node.id,
            target,
            label: "output",
            type: "inferred",
            confidence: null,
          });
        }
      });
    });
    return edges;
  }

  function normalizeGroups(rawGroups, nodes) {
    const groupMap = new Map();
    rawGroups.forEach((group, index) => {
      const id = String(group.id || group.key || group.name || group.label || `layer-${index + 1}`);
      groupMap.set(id, {
        id,
        label: String(group.label || group.name || id),
        type: String(group.type || group.kind || "layer"),
        notes: asStringArray(group.notes || group.description),
        count: 0,
        confidence: null,
      });
    });

    nodes.forEach((node) => {
      if (!groupMap.has(node.group)) {
        groupMap.set(node.group, {
          id: node.group,
          label: node.group,
          type: "layer",
          notes: [],
          count: 0,
          confidence: null,
        });
      }
      const group = groupMap.get(node.group);
      group.count += 1;
      if (node.confidence !== null) {
        group.confidence = group.confidence === null ? node.confidence : (group.confidence + node.confidence) / 2;
      }
    });

    return Array.from(groupMap.values()).sort((a, b) => a.label.localeCompare(b.label));
  }

  function normalizeRefs(value) {
    const refs = Array.isArray(value) ? value : value ? [value] : [];
    return refs.map((ref) => {
      if (typeof ref === "string") {
        return { path: ref };
      }
      return {
        path: String(ref.path || ref.file || ref.href || ref.id || "source"),
        line: ref.line || ref.start_line || ref.startLine || null,
        kind: ref.kind || ref.type || null,
      };
    });
  }

  function normalizePending(raw) {
    const list = coerceCollection(raw && (raw.pending || raw.items || raw.requests || raw));
    return list.map((item, index) => normalizePendingItem(item, index));
  }

  function normalizePendingItem(item, index) {
    const fields = item.fields || item.payload || {};
    const target = item.target || {};
    const targetLabel = target.node_label
      || target.node_id
      || target.group
      || (typeof item.target === "string" ? item.target : "")
      || item.path
      || "Canvas";
    return {
      id: String(item.id || item.key || item.path || `pending-${index + 1}`),
      kind: String(item.kind || item.type || fields.kind || "change_request"),
      title: String(item.title || fields.title || item.summary || labelFromKind(item.kind || item.type || "change request")),
      target: String(targetLabel),
      status: String(item.status || (item.localOnly ? "not sent" : "queued")),
      createdAt: item.created_at || item.createdAt || item.timestamp || null,
      path: item.path || item.markdown_path || item.md_path || "",
      localOnly: Boolean(item.localOnly),
      error: item.error || "",
    };
  }

  function render() {
    renderWorkspaceMeta();
    renderViewTabs();
    renderLayers();
    renderCanvas();
    renderInspector();
    renderPending();
  }

  function renderWorkspaceMeta() {
    const workspace = state.graphMeta.workspace || "Local workspace";
    els.workspaceLabel.textContent = workspace;
  }

  function renderViewTabs() {
    els.viewList.innerHTML = VIEW_DEFS.map((view) => {
      const active = view.id === state.activeView ? " is-active" : "";
      const count = viewCount(view.id);
      return `
        <button class="view-button${active}" type="button" data-view-id="${escapeAttr(view.id)}">
          <span>${escapeHtml(view.label)}</span>
          <strong>${count}</strong>
        </button>
      `;
    }).join("");

    els.viewList.querySelectorAll("[data-view-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeView = button.dataset.viewId;
        state.selectedNodeId = null;
        if (state.activeView !== "repo") {
          state.selectedGroupId = null;
        }
        render();
      });
    });
  }

  function renderLayers() {
    if (!state.groups.length) {
      els.layerList.innerHTML = `<p class="empty-copy">No layers detected.</p>`;
      return;
    }

    els.layerList.innerHTML = state.groups.map((group) => {
      const active = group.id === state.selectedGroupId ? " is-active" : "";
      const confidence = formatConfidence(group.confidence);
      return `
        <button class="layer-button${active}" type="button" data-group-id="${escapeAttr(group.id)}">
          <span>
            <strong>${escapeHtml(group.label)}</strong>
            <small>${escapeHtml(group.type)}${confidence ? ` - ${confidence}` : ""}</small>
          </span>
          <em>${group.count}</em>
        </button>
      `;
    }).join("");

    els.layerList.querySelectorAll("[data-group-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeView = "repo";
        state.selectedGroupId = button.dataset.groupId;
        state.selectedNodeId = null;
        setZoom(Math.max(state.zoom, 1.25), false);
        render();
      });
    });
  }

  function renderCanvas() {
    const view = VIEW_DEFS.find((item) => item.id === state.activeView) || VIEW_DEFS[0];
    const viewGraph = buildViewGraph();
    state.visibleNodes = viewGraph.nodes;
    state.visibleEdges = viewGraph.edges;
    state.layout = computeLayout(viewGraph.nodes, viewGraph.edges);

    const selectedGroup = state.groups.find((group) => group.id === state.selectedGroupId);
    els.viewTitle.textContent = selectedGroup && state.activeView === "repo" ? selectedGroup.label : view.label;
    els.viewSummary.textContent = selectedGroup && state.activeView === "repo"
      ? `${selectedGroup.count} node${selectedGroup.count === 1 ? "" : "s"} in this layer. Zoom or select nodes for detail.`
      : view.summary;

    const size = canvasSizeFromLayout(state.layout, viewGraph.nodes);
    els.edgeLayer.setAttribute("viewBox", `0 0 ${size.width} ${size.height}`);
    els.edgeLayer.style.width = `${size.width}px`;
    els.edgeLayer.style.height = `${size.height}px`;
    els.nodeLayer.style.width = `${size.width}px`;
    els.nodeLayer.style.height = `${size.height}px`;
    els.canvasContent.style.width = `${size.width}px`;
    els.canvasContent.style.height = `${size.height}px`;
    els.canvasContent.style.transform = `scale(${state.zoom})`;
    els.zoomFitButton.textContent = `${Math.round(state.zoom * 100)}%`;

    renderEdges(size);
    renderNodes();
  }

  function buildViewGraph() {
    if (state.activeView === "repo" && !state.selectedGroupId) {
      return buildRepoGroupGraph();
    }

    let nodes = state.nodes;
    if (state.activeView === "repo" && state.selectedGroupId) {
      nodes = state.nodes.filter((node) => node.group === state.selectedGroupId);
    } else if (state.activeView === "current") {
      const currentNodes = state.nodes.filter((node) => node.current || node.notes.length || node.confidence === null || node.confidence < 0.68);
      nodes = currentNodes.length ? includeNeighbors(currentNodes) : state.nodes.slice(0, 10);
    } else if (state.activeView === "routes") {
      const routeNodes = state.nodes.filter((node) => node.routeLike);
      nodes = routeNodes.length ? includeNeighbors(routeNodes) : state.nodes.filter((node) => hasAnyEdge(node.id));
    } else if (state.activeView === "tests") {
      const testNodes = state.nodes.filter((node) => node.testLike);
      nodes = testNodes.length ? includeNeighbors(testNodes) : state.nodes.slice(-8);
    }

    const ids = new Set(nodes.map((node) => node.id));
    const edges = state.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    return { nodes, edges };
  }

  function buildRepoGroupGraph() {
    const groupNodes = state.groups.map((group) => ({
      id: `group:${group.id}`,
      label: group.label,
      type: group.type,
      group: group.id,
      confidence: group.confidence,
      sourceRefs: [],
      inputs: [],
      outputs: [],
      notes: group.notes,
      count: group.count,
      isGroup: true,
    }));

    const nodeGroup = new Map(state.nodes.map((node) => [node.id, node.group]));
    const edgeMap = new Map();
    state.edges.forEach((edge) => {
      const sourceGroup = nodeGroup.get(edge.source);
      const targetGroup = nodeGroup.get(edge.target);
      if (!sourceGroup || !targetGroup || sourceGroup === targetGroup) {
        return;
      }
      const key = `${sourceGroup}->${targetGroup}`;
      if (!edgeMap.has(key)) {
        edgeMap.set(key, {
          id: `group-edge:${key}`,
          source: `group:${sourceGroup}`,
          target: `group:${targetGroup}`,
          label: "depends on",
          type: "layer",
          confidence: null,
        });
      }
    });

    return { nodes: groupNodes, edges: Array.from(edgeMap.values()) };
  }

  function includeNeighbors(seedNodes) {
    const ids = new Set(seedNodes.map((node) => node.id));
    state.edges.forEach((edge) => {
      if (ids.has(edge.source)) {
        ids.add(edge.target);
      }
      if (ids.has(edge.target)) {
        ids.add(edge.source);
      }
    });
    return state.nodes.filter((node) => ids.has(node.id));
  }

  function hasAnyEdge(nodeId) {
    return state.edges.some((edge) => edge.source === nodeId || edge.target === nodeId);
  }

  function computeLayout(nodes, edges) {
    const layout = new Map();
    if (!nodes.length) {
      return layout;
    }

    const groupMode = nodes.every((node) => node.isGroup);
    if (groupMode) {
      const columns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(nodes.length))));
      nodes.forEach((node, index) => {
        const column = index % columns;
        const row = Math.floor(index / columns);
        layout.set(node.id, {
          x: 70 + column * 340,
          y: 64 + row * 210,
          width: 286,
          height: 150,
        });
      });
      return layout;
    }

    const levels = computeLevels(nodes, edges);
    const byLevel = new Map();
    nodes.forEach((node, index) => {
      const level = levels.get(node.id) ?? index % 4;
      if (!byLevel.has(level)) {
        byLevel.set(level, []);
      }
      byLevel.get(level).push(node);
    });

    Array.from(byLevel.keys()).sort((a, b) => a - b).forEach((level) => {
      const levelNodes = byLevel.get(level);
      levelNodes.forEach((node, row) => {
        layout.set(node.id, {
          x: 70 + level * 300,
          y: 56 + row * 150,
          width: 232,
          height: 112,
        });
      });
    });

    return layout;
  }

  function computeLevels(nodes, edges) {
    const ids = new Set(nodes.map((node) => node.id));
    const levels = new Map(nodes.map((node) => [node.id, 0]));
    const visibleEdges = edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));

    for (let pass = 0; pass < nodes.length; pass += 1) {
      let changed = false;
      visibleEdges.forEach((edge) => {
        const nextLevel = (levels.get(edge.source) || 0) + 1;
        if (nextLevel > (levels.get(edge.target) || 0)) {
          levels.set(edge.target, nextLevel);
          changed = true;
        }
      });
      if (!changed) {
        break;
      }
    }

    const maxLevel = Math.max(0, ...Array.from(levels.values()));
    if (maxLevel > 5) {
      nodes.forEach((node, index) => levels.set(node.id, index % 4));
    }
    return levels;
  }

  function canvasSizeFromLayout(layout, nodes) {
    let width = 980;
    let height = 560;
    nodes.forEach((node) => {
      const box = layout.get(node.id);
      if (!box) {
        return;
      }
      width = Math.max(width, box.x + box.width + 120);
      height = Math.max(height, box.y + box.height + 100);
    });
    return { width, height };
  }

  function renderEdges(size) {
    const paths = state.visibleEdges.map((edge) => {
      const source = state.layout.get(edge.source);
      const target = state.layout.get(edge.target);
      if (!source || !target) {
        return "";
      }
      const start = { x: source.x + source.width, y: source.y + source.height / 2 };
      const end = { x: target.x, y: target.y + target.height / 2 };
      const distance = Math.max(68, Math.abs(end.x - start.x) / 2);
      const d = `M ${start.x} ${start.y} C ${start.x + distance} ${start.y}, ${end.x - distance} ${end.y}, ${end.x} ${end.y}`;
      const labelX = (start.x + end.x) / 2;
      const labelY = (start.y + end.y) / 2 - 8;
      return `
        <path class="edge-path" d="${d}" marker-end="url(#arrowHead)"></path>
        ${edge.label ? `<text class="edge-label" x="${labelX}" y="${labelY}" data-edge-id="${escapeAttr(edge.id)}">${escapeHtml(edge.label)}</text>` : ""}
      `;
    }).join("");

    els.edgeLayer.innerHTML = `
      <defs>
        <marker id="arrowHead" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z"></path>
        </marker>
      </defs>
      <rect class="canvas-grid" x="0" y="0" width="${size.width}" height="${size.height}"></rect>
      ${paths}
    `;

    els.edgeLayer.querySelectorAll("[data-edge-id]").forEach((label) => {
      label.addEventListener("click", () => {
        const edge = state.visibleEdges.find((item) => item.id === label.dataset.edgeId);
        openRequestDialog("reroute_edge", { edge });
      });
    });
  }

  function renderNodes() {
    if (!state.visibleNodes.length) {
      els.nodeLayer.innerHTML = `<div class="canvas-empty">No nodes match this view.</div>`;
      return;
    }

    els.nodeLayer.innerHTML = state.visibleNodes.map((node) => {
      const box = state.layout.get(node.id);
      const selected = node.id === state.selectedNodeId ? " is-selected" : "";
      const lowConfidence = node.confidence !== null && node.confidence < 0.6 ? " is-low-confidence" : "";
      const groupClass = node.isGroup ? " is-group" : "";
      const confidence = formatConfidence(node.confidence);
      const refs = node.sourceRefs && node.sourceRefs.length ? `${node.sourceRefs.length} ref${node.sourceRefs.length === 1 ? "" : "s"}` : "No refs";
      const detail = node.isGroup ? `${node.count || 0} node${node.count === 1 ? "" : "s"}` : refs;
      return `
        <article class="canvas-node${selected}${lowConfidence}${groupClass}" data-node-id="${escapeAttr(node.id)}" tabindex="0" role="button"
          style="left:${box.x}px; top:${box.y}px; width:${box.width}px; min-height:${box.height}px">
          <header>
            <span class="node-type">${escapeHtml(node.type)}</span>
            ${confidence ? `<span class="node-confidence">${confidence}</span>` : ""}
          </header>
          <h3>${escapeHtml(node.label)}</h3>
          <p>${escapeHtml(detail)}</p>
          ${node.notes && node.notes.length ? `<small>${escapeHtml(node.notes[0])}</small>` : ""}
        </article>
      `;
    }).join("");

    els.nodeLayer.querySelectorAll("[data-node-id]").forEach((nodeEl) => {
      const select = () => {
        const id = nodeEl.dataset.nodeId;
        const node = state.visibleNodes.find((item) => item.id === id);
        if (node && node.isGroup) {
          state.activeView = "repo";
          state.selectedGroupId = node.group;
          state.selectedNodeId = null;
          setZoom(Math.max(state.zoom, 1.25), false);
          render();
          return;
        }
        state.selectedNodeId = id;
        renderInspector();
        renderCanvasSelection();
      };
      nodeEl.addEventListener("click", select);
      nodeEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
    });
  }

  function renderCanvasSelection() {
    els.nodeLayer.querySelectorAll("[data-node-id]").forEach((nodeEl) => {
      nodeEl.classList.toggle("is-selected", nodeEl.dataset.nodeId === state.selectedNodeId);
    });
  }

  function renderInspector() {
    const node = selectedNode();
    if (!node) {
      const group = state.groups.find((item) => item.id === state.selectedGroupId);
      els.inspector.innerHTML = `
        <section class="inspector-block">
          <h2>${group ? escapeHtml(group.label) : "Inspector"}</h2>
          <p class="muted">${group ? `${group.count} nodes in this repo layer.` : "Select a node or layer to inspect source refs, flow, and queued actions."}</p>
        </section>
        <section class="inspector-block action-stack">
          <button class="button button-secondary" type="button" data-action="add_note">Add canvas note</button>
          <button class="button button-primary" type="button" data-action="add_node">Add node request</button>
          <button class="button button-warning" type="button" data-action="request_test_coverage">Request test coverage</button>
        </section>
      `;
      bindInspectorActions();
      return;
    }

    els.inspector.innerHTML = `
      <section class="inspector-block inspector-title">
        <span class="node-type">${escapeHtml(node.type)}</span>
        <h2>${escapeHtml(node.label)}</h2>
        <p>${escapeHtml(node.id)}</p>
      </section>

      <section class="inspector-block metric-grid">
        <div>
          <strong>${formatConfidence(node.confidence) || "n/a"}</strong>
          <span>Confidence</span>
        </div>
        <div>
          <strong>${escapeHtml(node.group)}</strong>
          <span>Layer</span>
        </div>
      </section>

      <section class="inspector-block">
        <h3>Source refs</h3>
        ${renderRefs(node.sourceRefs)}
      </section>

      <section class="inspector-block two-column-list">
        <div>
          <h3>Inputs</h3>
          ${renderChips(node.inputs, "No inputs")}
        </div>
        <div>
          <h3>Outputs</h3>
          ${renderChips(node.outputs, "No outputs")}
        </div>
      </section>

      <section class="inspector-block">
        <h3>Notes</h3>
        ${node.notes.length ? `<ul class="notes-list">${node.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : `<p class="muted">No notes on this node.</p>`}
      </section>

      <section class="inspector-block action-stack">
        <button class="button button-secondary" type="button" data-action="add_note">Add note</button>
        <button class="button button-secondary" type="button" data-action="add_node">Add node near this</button>
        <button class="button button-secondary" type="button" data-action="change_node_flow">Change node flow</button>
        <button class="button button-warning" type="button" data-action="request_test_coverage">Request test coverage</button>
        <button class="button button-danger" type="button" data-action="reroute_edge">Re-route edge</button>
        <button class="button button-danger" type="button" data-action="remove_node">Remove node request</button>
      </section>
    `;
    bindInspectorActions();
  }

  function renderRefs(refs) {
    if (!refs || !refs.length) {
      return `<p class="muted">No source refs reported.</p>`;
    }
    return `
      <div class="source-ref-list">
        ${refs.map((ref) => {
          const label = `${ref.path}${ref.line ? `:${ref.line}` : ""}`;
          return `<button class="source-ref" type="button" title="${escapeAttr(label)}">${escapeHtml(label)}</button>`;
        }).join("")}
      </div>
    `;
  }

  function renderChips(items, emptyText) {
    if (!items || !items.length) {
      return `<p class="muted">${escapeHtml(emptyText)}</p>`;
    }
    return `<div class="chip-list">${items.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`;
  }

  function bindInspectorActions() {
    els.inspector.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => openRequestDialog(button.dataset.action));
    });
  }

  function renderPending() {
    const count = state.pending.length;
    const source = state.apiStatus.pending === "live" ? "from /api/pending" : "local session only";
    els.queueSummary.textContent = `${count} request${count === 1 ? "" : "s"} ${source}`;

    if (!count) {
      els.pendingList.innerHTML = `<p class="empty-copy">No pending change requests yet.</p>`;
      return;
    }

    els.pendingList.innerHTML = state.pending.map((item) => `
      <article class="pending-item">
        <div>
          <span class="pending-kind">${escapeHtml(labelFromKind(item.kind))}</span>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.target)}${item.path ? ` - ${escapeHtml(item.path)}` : ""}</p>
        </div>
        <span class="pending-status${item.localOnly ? " is-local" : ""}">${escapeHtml(item.status)}</span>
      </article>
    `).join("");
  }

  function openRequestDialog(kind, options = {}) {
    const def = REQUEST_DEFS[kind] || REQUEST_DEFS.add_note;
    const node = selectedNode();
    const edge = options.edge;
    const targetLabel = edge
      ? `${edge.source} -> ${edge.target}`
      : node
        ? node.label
        : state.selectedGroupId || "Canvas";

    els.requestDialog.dataset.kind = kind;
    els.requestDialog.dataset.edgeId = edge ? edge.id : "";
    els.requestTitle.textContent = def.title;
    els.requestTarget.textContent = targetLabel;
    els.submitRequestButton.classList.toggle("button-danger", def.tone === "danger");
    els.submitRequestButton.classList.toggle("button-warning", def.tone === "warning");

    els.requestFields.innerHTML = def.fields.map((field) => {
      const value = defaultFieldValue(field, kind, node, edge);
      const required = field.required ? " required" : "";
      if (field.type === "textarea") {
        return `
          <label>
            <span>${escapeHtml(field.label)}</span>
            <textarea name="${escapeAttr(field.id)}"${required}>${escapeHtml(value)}</textarea>
          </label>
        `;
      }
      return `
        <label>
          <span>${escapeHtml(field.label)}</span>
          <input name="${escapeAttr(field.id)}" value="${escapeAttr(value)}"${required} />
        </label>
      `;
    }).join("");

    if (typeof els.requestDialog.showModal === "function") {
      els.requestDialog.showModal();
      const firstInput = els.requestDialog.querySelector("input, textarea");
      if (firstInput) {
        firstInput.focus();
      }
    }
  }

  function defaultFieldValue(field, kind, node, edge) {
    if (field.value) {
      return field.value;
    }
    if (field.id === "from_node") {
      return edge ? edge.source : node ? node.id : "";
    }
    if (field.id === "to_node") {
      return edge ? edge.target : "";
    }
    if (field.id === "coverage_target") {
      return node ? node.label : state.selectedGroupId || "";
    }
    if (field.id === "label" && kind === "add_node") {
      return node ? `${node.label} follow-up` : "";
    }
    return "";
  }

  async function handleRequestSubmit(event) {
    if (event.submitter && event.submitter.value === "cancel") {
      return;
    }
    event.preventDefault();

    const kind = els.requestDialog.dataset.kind;
    const node = selectedNode();
    const edge = state.visibleEdges.find((item) => item.id === els.requestDialog.dataset.edgeId);
    const formData = new FormData(els.requestForm);
    const fields = {};
    formData.forEach((value, key) => {
      fields[key] = String(value).trim();
    });

    const payload = {
      kind,
      title: REQUEST_DEFS[kind] ? REQUEST_DEFS[kind].title : labelFromKind(kind),
      target: {
        view: state.activeView,
        group: state.selectedGroupId,
        node_id: node ? node.id : null,
        node_label: node ? node.label : null,
        edge_id: edge ? edge.id : null,
        edge_source: edge ? edge.source : null,
        edge_target: edge ? edge.target : null,
      },
      fields,
      graph_revision: state.graphMeta.revision || state.graphMeta.generated_at || null,
      created_from: "agentcanvas-web",
    };

    els.submitRequestButton.disabled = true;
    try {
      const response = await fetchJson("/api/changes", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const responseItem = response && typeof response === "object"
        ? response.pending || response.request || response
        : {};
      const item = normalizePendingItem(responseItem, 0);
      state.pending.unshift({
        ...item,
        id: item.id || `queued-${Date.now()}`,
        kind,
        title: item.title || payload.title,
        target: item.target !== "Canvas" ? item.target : payload.target.node_label || payload.target.group || "Canvas",
        status: item.status || "queued",
      });
      state.apiStatus.pending = "live";
      els.requestDialog.close();
    } catch (error) {
      state.pending.unshift({
        id: `local-${Date.now()}`,
        kind,
        title: payload.title,
        target: payload.target.node_label || payload.target.group || "Canvas",
        status: "not sent",
        localOnly: true,
        error: error.message,
      });
      state.apiStatus.pending = "fallback";
      els.requestDialog.close();
    } finally {
      els.submitRequestButton.disabled = false;
      renderPending();
    }
  }

  function selectedNode() {
    if (!state.selectedNodeId) {
      return null;
    }
    return state.nodes.find((node) => node.id === state.selectedNodeId)
      || state.visibleNodes.find((node) => node.id === state.selectedNodeId)
      || null;
  }

  function setZoom(nextZoom, shouldRender = true) {
    state.zoom = clamp(Number(nextZoom), 0.65, 1.75);
    if (shouldRender) {
      renderCanvas();
    }
  }

  function viewCount(viewId) {
    if (viewId === "repo") {
      return state.groups.length || state.nodes.length;
    }
    if (viewId === "routes") {
      return state.edges.length;
    }
    if (viewId === "tests") {
      return state.nodes.filter((node) => node.testLike).length;
    }
    return state.nodes.filter((node) => node.current || node.notes.length || (node.confidence !== null && node.confidence < 0.68)).length || state.nodes.length;
  }

  function setGraphStatus(message, tone) {
    els.graphStatus.textContent = message;
    els.graphStatus.dataset.tone = tone;
  }

  function updateTokenStatus() {
    const token = new URLSearchParams(window.location.search).get("token");
    els.tokenStatus.textContent = token ? "Token preserved" : "Local";
    els.tokenStatus.classList.toggle("is-token", Boolean(token));
  }

  function pick(object, keys) {
    if (!object || typeof object !== "object") {
      return undefined;
    }
    for (const key of keys) {
      if (object[key] !== undefined && object[key] !== null) {
        return object[key];
      }
    }
    return undefined;
  }

  function coerceCollection(value) {
    if (!value) {
      return [];
    }
    if (Array.isArray(value)) {
      return value;
    }
    if (typeof value === "object") {
      return Object.entries(value).map(([key, item]) => {
        if (item && typeof item === "object" && !Array.isArray(item)) {
          return { id: key, ...item };
        }
        return { id: key, value: item };
      });
    }
    return [];
  }

  function asStringArray(value) {
    if (value === undefined || value === null || value === "") {
      return [];
    }
    if (Array.isArray(value)) {
      return value.map((item) => stringifyValue(item)).filter(Boolean);
    }
    return [stringifyValue(value)].filter(Boolean);
  }

  function stringifyValue(value) {
    if (value === undefined || value === null) {
      return "";
    }
    if (typeof value === "object") {
      return String(value.label || value.name || value.id || value.path || JSON.stringify(value));
    }
    return String(value);
  }

  function inferType(label, refs) {
    const text = `${label} ${refs.map((ref) => ref.path).join(" ")}`.toLowerCase();
    if (text.includes("test") || text.includes("spec")) return "test";
    if (text.includes("route") || text.includes("api")) return "route";
    if (text.includes("readme") || text.includes("doc")) return "doc";
    if (text.includes("server")) return "server";
    if (text.includes("web") || text.includes("ui")) return "ui";
    return "node";
  }

  function inferGroup(type, refs) {
    const path = refs[0] && refs[0].path ? refs[0].path : "";
    if (type === "test") return "Tests";
    if (path.includes("/web/")) return "Web UI";
    if (path.includes("server")) return "Server";
    if (path.includes("index")) return "Index";
    if (path.includes("README") || path.includes("docs")) return "Docs";
    return "Workflow";
  }

  function isTestLike(type, label, refs) {
    const text = `${type} ${label} ${refs.map((ref) => ref.path).join(" ")}`.toLowerCase();
    return text.includes("test") || text.includes("spec") || text.includes("coverage");
  }

  function isRouteLike(type, label, refs) {
    const text = `${type} ${label} ${refs.map((ref) => ref.path).join(" ")}`.toLowerCase();
    return text.includes("route") || text.includes("api") || text.includes("server") || text.includes("handler") || text.includes("edge");
  }

  function lastPathSegment(path) {
    return path ? String(path).split("/").filter(Boolean).pop() : "";
  }

  function formatConfidence(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "";
    }
    return `${Math.round(Number(value) * 100)}%`;
  }

  function labelFromKind(kind) {
    return String(kind || "change request")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }
})();
