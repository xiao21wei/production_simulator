const STATUS_TEXT = {
  idle: "等待启动",
  preparing: "准备数据",
  running: "仿真运行中",
  paused: "仿真已暂停",
  reoptimizing: "重调度中 · 仿真已暂停",
  stopping: "正在停止",
  stopped: "仿真已停止",
  finished: "仿真完成",
  failed: "运行失败",
};

const EVENT_TEXT = {
  OperationStartEvent: "工序开始",
  OperationFinishEvent: "工序完成",
  TransportFinishEvent: "运输完成",
  JobSubmitEvent: "作业提交",
  JobStartEvent: "作业开始",
  JobFinishEvent: "作业完成",
  ScheduleEvent: "生成排程",
  OrderInsertEvent: "插单",
  OrderCancelEvent: "订单取消",
  MachineAnomalyEvent: "设备异常",
  MachineRecoveryEvent: "设备恢复",
};

const ANOMALY_LIST_EVENT_TYPES = new Set([
  "OrderInsertEvent",
  "OrderCancelEvent",
  "MachineAnomalyEvent",
  "MachineRecoveryEvent",
]);

const JOB_STATUS_TEXT = {
  processing: "加工中",
  completed: "已完成",
  canceled: "已取消",
};

const JOB_GROUPS = [
  { status: "processing", label: "加工中" },
  { status: "completed", label: "已完成" },
  { status: "canceled", label: "已取消" },
];

const DEFAULT_JOB_GROUP_OPEN = {
  processing: false,
  completed: false,
  canceled: false,
};

const ORDER_SOURCE_TEXT = {
  initial: "初始订单",
  auto: "自动插单",
  manual: "手动插单",
};

const ORDER_STATUS_TEXT = {
  processing: "进行中",
  completed: "已完成",
  canceled: "已取消",
  mixed: "部分完成",
};

const elements = {
  anomalyCount: document.querySelector("#anomaly-count"),
  anomalyDialog: document.querySelector("#anomaly-dialog"),
  anomalyDialogClose: document.querySelector("#anomaly-dialog-close"),
  anomalyDialogDismiss: document.querySelector("#anomaly-dialog-dismiss"),
  anomalyDuration: document.querySelector("#anomaly-duration"),
  anomalyDurationHint: document.querySelector("#anomaly-duration-hint"),
  anomalyList: document.querySelector("#anomaly-list"),
  anomalyMachineSelect: document.querySelector("#anomaly-machine-select"),
  anomalyTypeSelect: document.querySelector("#anomaly-type-select"),
  autoMachineAnomaly: document.querySelector("#auto-machine-anomaly"),
  autoJobSubmit: document.querySelector("#auto-job-submit"),
  cancelDialogClose: document.querySelector("#cancel-dialog-close"),
  cancelDialogDismiss: document.querySelector("#cancel-dialog-dismiss"),
  cancelJobOptions: document.querySelector("#cancel-job-options"),
  cancelOrderOptions: document.querySelector("#cancel-order-options"),
  cancelJobsButton: document.querySelector("#cancel-jobs-button"),
  cancelJobsDialog: document.querySelector("#cancel-jobs-dialog"),
  cancelSelectionCount: document.querySelector("#cancel-selection-count"),
  cancelSelectAll: document.querySelector("#cancel-select-all"),
  clockReadout: document.querySelector("#clock-readout"),
  confirmCancelJobs: document.querySelector("#confirm-cancel-jobs"),
  connectionStatus: document.querySelector("#connection-status"),
  currentTime: document.querySelector("#current-time"),
  datasetSelect: document.querySelector("#dataset-select"),
  deliveryPenalty: document.querySelector("#delivery-penalty"),
  displaySelect: document.querySelector("#display-select"),
  errorBanner: document.querySelector("#error-banner"),
  confirmAnomaly: document.querySelector("#confirm-anomaly"),
  finishedJobs: document.querySelector("#finished-jobs"),
  jobCount: document.querySelector("#job-count"),
  jobList: document.querySelector("#job-list"),
  insertAnomalyButton: document.querySelector("#insert-anomaly-button"),
  machineBoardSummary: document.querySelector("#machine-board-summary"),
  machineBoardTab: document.querySelector("#machine-board-tab"),
  machineBoardView: document.querySelector("#machine-board-view"),
  machineCardGrid: document.querySelector("#machine-card-grid"),
  manualJobInsertButton: document.querySelector(
    "#manual-job-insert-button"
  ),
  machineLanes: document.querySelector("#machine-lanes"),
  makespan: document.querySelector("#makespan"),
  orderCount: document.querySelector("#order-count"),
  orderList: document.querySelector("#order-list"),
  pauseButton: document.querySelector("#pause-button"),
  playhead: document.querySelector("#playhead"),
  reoptimizeButton: document.querySelector("#reoptimize-button"),
  reoptimizerSelect: document.querySelector("#reoptimizer-select"),
  scheduleTab: document.querySelector("#schedule-tab"),
  scheduleView: document.querySelector("#schedule-view"),
  speedSelect: document.querySelector("#speed-select"),
  startButton: document.querySelector("#start-button"),
  stopButton: document.querySelector("#stop-button"),
  timeAxis: document.querySelector("#time-axis"),
  timelineBody: document.querySelector("#timeline-body"),
  totalEnergy: document.querySelector("#total-energy"),
};

const app = {
  after: 0,
  generation: null,
  horizon: 100,
  visibleSpan: 100,
  currentTime: 0,
  serverTime: 0,
  lastServerTime: 0,
  lastSyncAt: performance.now(),
  lastAxisRenderAt: 0,
  lastFrameRenderAt: 0,
  datasetsReady: false,
  datasetCatalog: [],
  displayPercent: 100,
  speed: 5,
  status: "idle",
  lanes: new Map(),
  bars: new Map(),
  transportSegments: new Map(),
  nextOperationStart: new Map(),
  pendingSignatures: new Map(),
  planRevision: null,
  jobGroupOpen: { ...DEFAULT_JOB_GROUP_OPEN },
  jobGroups: new Map(),
  jobStates: [],
  orderBatches: [],
  orderListSignature: null,
  cancelRequestPending: false,
  anomalyCount: 0,
  machineStates: [],
  machineCards: new Map(),
  machineDetection: new Map(),
  detectionBuffers: new Map(),
  detectionMachines: [],
  detectionMachineCount: null,
  detectionFields: [],
  detectionHistoryPoints: 60,
  detectionPredictionHorizon: 20,
  detectionPredictionInterval: 5,
  detectionLastPredictionT: null,
  detectionPredictionError: null,
  detectionPollInterval: 1000,
  detectionT: 0,
  detectionTimer: null,
  detectionLoading: false,
  detectionInitializing: false,
  detectionStreamGeneration: null,
  detectionError: null,
  activeTab: "schedule",
};
let pollTimer = null;

function formatTime(value) {
  return Number(value || 0).toFixed(value < 10 ? 1 : 0);
}

function operationKey(jobId, operationId) {
  return `${jobId}-${operationId}`;
}

function jobHue(jobId) {
  return (185 + Number(jobId) * 137.508) % 360;
}

function resetView() {
  app.after = 0;
  app.lanes.clear();
  app.bars.clear();
  app.transportSegments.clear();
  app.nextOperationStart.clear();
  app.pendingSignatures.clear();
  app.planRevision = null;
  app.jobGroupOpen = { ...DEFAULT_JOB_GROUP_OPEN };
  app.jobGroups.clear();
  app.jobStates = [];
  app.orderBatches = [];
  app.orderListSignature = null;
  app.cancelRequestPending = false;
  app.anomalyCount = 0;
  app.machineStates = [];
  app.horizon = 100;
  app.visibleSpan = 100;
  app.currentTime = 0;
  app.serverTime = 0;
  app.lastServerTime = 0;
  app.lastSyncAt = performance.now();
  app.lastAxisRenderAt = 0;
  app.lastFrameRenderAt = 0;
  app.displayPercent = 100;
  elements.machineLanes.replaceChildren();
  elements.anomalyList.replaceChildren();
  const anomalyEmpty = document.createElement("div");
  anomalyEmpty.className = "empty-state";
  anomalyEmpty.textContent = "暂无异常事件";
  elements.anomalyList.append(anomalyEmpty);
  elements.jobList.replaceChildren();
  elements.orderList.replaceChildren();
  elements.anomalyCount.textContent = "0";
  elements.jobCount.textContent = "0";
  elements.timelineBody.scrollTop = 0;
  setDashboardTab(app.activeTab);
}

function setDashboardTab(tab) {
  app.activeTab = tab === "machine-board" ? "machine-board" : "schedule";
  const showingSchedule = app.activeTab === "schedule";
  elements.scheduleView.classList.toggle("hidden", !showingSchedule);
  elements.machineBoardView.classList.toggle("hidden", showingSchedule);
  elements.scheduleTab.classList.toggle("active", showingSchedule);
  elements.machineBoardTab.classList.toggle("active", !showingSchedule);
  elements.scheduleTab.setAttribute(
    "aria-selected",
    String(showingSchedule),
  );
  elements.machineBoardTab.setAttribute(
    "aria-selected",
    String(!showingSchedule),
  );
  if (!showingSchedule) {
    window.requestAnimationFrame(() => {
      renderMachineDetectionCharts();
      resizeMachineCharts();
    });
  }
}

function enableTimelineWheelScroll() {
  elements.timelineBody.addEventListener(
    "wheel",
    (event) => {
      const maxScroll =
        elements.timelineBody.scrollHeight
        - elements.timelineBody.clientHeight;
      if (maxScroll <= 0 || event.ctrlKey) {
        return;
      }
      event.preventDefault();
      elements.timelineBody.scrollTop = Math.max(
        0,
        Math.min(maxScroll, elements.timelineBody.scrollTop + event.deltaY),
      );
    },
    { passive: false },
  );
}

function ensureLane(machineId) {
  if (app.lanes.has(machineId)) {
    return app.lanes.get(machineId);
  }

  const lane = document.createElement("div");
  lane.className = "machine-lane";

  const label = document.createElement("div");
  label.className = "machine-label";
  label.innerHTML = `<strong>M${String(machineId).padStart(2, "0")}</strong><span></span>`;

  const track = document.createElement("div");
  track.className = "machine-lane-track";
  const pendingQueue = document.createElement("div");
  pendingQueue.className = "pending-queue";
  lane.append(label, track, pendingQueue);

  const nextMachineId = [...app.lanes.keys()]
    .filter((id) => id > machineId)
    .sort((left, right) => left - right)[0];
  if (nextMachineId === undefined) {
    elements.machineLanes.append(lane);
  } else {
    elements.machineLanes.insertBefore(
      lane,
      app.lanes.get(nextMachineId).lane,
    );
  }

  const entry = {
    lane,
    label,
    track,
    pendingQueue,
    status: label.querySelector("span"),
  };
  app.lanes.set(machineId, entry);
  return entry;
}

function ensureBar(operation) {
  const key = operationKey(operation.job_id, operation.operation_id);
  let bar = app.bars.get(key);
  const lane = ensureLane(operation.machine_id);
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "operation-bar";
    bar.style.setProperty("--bar-hue", jobHue(operation.job_id));
    bar.dataset.key = key;
    bar.dataset.start = operation.start_time;
    bar.dataset.end = operation.end_time;
    bar.dataset.machine = operation.machine_id;
    bar.textContent = `J${operation.job_id}-O${operation.operation_id}`;
    bar.title =
      `作业 ${operation.job_id} / 工序 ${operation.operation_id} / `
      + `M${operation.machine_id} / ${operation.start_time}-${operation.end_time}`;
    lane.track.append(bar);
    app.bars.set(key, bar);
  }
  positionBar(bar);
  return bar;
}

function positionBar(bar) {
  const start = Number(bar.dataset.start);
  const end = Number(bar.dataset.end);
  const startOffset = start - app.currentTime;
  const endOffset = end - app.currentTime;
  const halfSpan = app.visibleSpan / 2;
  const outside = endOffset < -halfSpan || startOffset > halfSpan;
  bar.hidden = outside;
  if (outside) {
    return;
  }

  const left = 50 + (startOffset / app.visibleSpan) * 100;
  const actualWidth = ((end - start) / app.visibleSpan) * 100;
  const nextStart = app.nextOperationStart.get(bar.dataset.key);
  const availableWidth = nextStart === undefined
    ? Number.POSITIVE_INFINITY
    : ((nextStart - start) / app.visibleSpan) * 100;
  const width = Math.max(
    actualWidth,
    Math.min(2.8, Math.max(0, availableWidth)),
  );
  const leftValue = `${left}%`;
  const widthValue = `${width}%`;
  if (bar.style.left !== leftValue) {
    bar.style.left = leftValue;
  }
  if (bar.style.width !== widthValue) {
    bar.style.width = widthValue;
  }
}

function ensureTransportSegment(operation, segmentData, index) {
  const key = [
    operationKey(operation.job_id, operation.operation_id),
    index,
  ].join("-");
  let segment = app.transportSegments.get(key);
  const lane = ensureLane(segmentData.target_machine);
  if (!segment) {
    segment = document.createElement("div");
    segment.className = "transport-segment";
    app.transportSegments.set(key, segment);
  }

  if (segment.parentElement !== lane.track) {
    lane.track.append(segment);
  }
  segment.dataset.start = segmentData.transport_start;
  segment.dataset.end = segmentData.transport_end;
  segment.dataset.sourceMachine = segmentData.source_machine;
  segment.dataset.targetMachine = segmentData.target_machine;
  segment.style.setProperty("--bar-hue", jobHue(operation.job_id));
  segment.textContent =
    `M${segmentData.source_machine}→M${segmentData.target_machine}`;
  segment.title =
    `机器间运输：M${segmentData.source_machine} → `
    + `M${segmentData.target_machine} / `
    + `运输时间 ${segmentData.transport_time} / `
    + `运输能耗 ${segmentData.transport_energy} / `
    + `目标机器等待 ${operation.waiting_time}`;
  return segment;
}

function syncTransportPlan(plan) {
  const desiredKeys = new Set();
  for (const operation of plan || []) {
    const segments = Array.isArray(operation.transport_segments)
      ? operation.transport_segments
      : [];
    for (const [index, segmentData] of segments.entries()) {
      const key = [
        operationKey(operation.job_id, operation.operation_id),
        index,
      ].join("-");
      desiredKeys.add(key);
      ensureTransportSegment(operation, segmentData, index);
    }
  }
  for (const [key, segment] of app.transportSegments.entries()) {
    if (!desiredKeys.has(key)) {
      segment.remove();
      app.transportSegments.delete(key);
    }
  }
}

function positionTransportSegment(segment) {
  const start = Number(segment.dataset.start);
  const end = Number(segment.dataset.end);
  if (app.currentTime < start) {
    segment.hidden = true;
    return;
  }

  const startOffset = start - app.currentTime;
  const endOffset = end - app.currentTime;
  const halfSpan = app.visibleSpan / 2;
  const outside = endOffset < -halfSpan || startOffset > halfSpan;
  segment.hidden = outside;
  if (outside) {
    return;
  }

  const left = 50 + (startOffset / app.visibleSpan) * 100;
  const width = Math.max(0.6, ((end - start) / app.visibleSpan) * 100);
  const leftValue = `${left}%`;
  const widthValue = `${width}%`;
  if (segment.style.left !== leftValue) {
    segment.style.left = leftValue;
  }
  if (segment.style.width !== widthValue) {
    segment.style.width = widthValue;
  }
  const isActive = app.currentTime >= start && app.currentTime < end;
  const isCompleted = app.currentTime >= end;
  if (segment.classList.contains("active") !== isActive) {
    segment.classList.toggle("active", isActive);
  }
  if (segment.classList.contains("completed") !== isCompleted) {
    segment.classList.toggle("completed", isCompleted);
  }
}

function refreshTransportSegments(currentTime) {
  app.currentTime = currentTime;
  for (const segment of app.transportSegments.values()) {
    positionTransportSegment(segment);
  }
}

function renderPlan(plan) {
  app.nextOperationStart.clear();
  const machinePlans = new Map();
  for (const operation of plan || []) {
    if (!machinePlans.has(operation.machine_id)) {
      machinePlans.set(operation.machine_id, []);
    }
    machinePlans.get(operation.machine_id).push(operation);
  }
  for (const operations of machinePlans.values()) {
    operations.sort((left, right) => left.start_time - right.start_time);
    for (let index = 0; index < operations.length - 1; index += 1) {
      const operation = operations[index];
      const nextOperation = operations[index + 1];
      app.nextOperationStart.set(
        operationKey(operation.job_id, operation.operation_id),
        nextOperation.start_time,
      );
    }
  }
  syncTransportPlan(plan);

  const planEnd = Math.max(
    0,
    ...((plan || []).map((operation) => operation.end_time)),
  );
  updateHorizon(planEnd);
  refreshBarStates(app.currentTime);
}

function updateHorizon(nextHorizon) {
  if (nextHorizon <= app.horizon) {
    return;
  }
  app.horizon = Math.max(100, Math.ceil(nextHorizon));
  updateVisibleSpan();
  for (const bar of app.bars.values()) {
    positionBar(bar);
  }
  renderAxis();
  renderPlayhead();
}

function updateVisibleSpan() {
  const baseSpan = Math.max(
    60,
    Math.min(150, Math.ceil(app.horizon / 6)),
  );
  app.visibleSpan = baseSpan / (app.displayPercent / 100);
}

function syncDisplaySelect(percent) {
  const value = String(Math.round(percent));
  if (![...elements.displaySelect.options].some((option) => option.value === value)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = `${value}%`;
    elements.displaySelect.append(option);
  }
  elements.displaySelect.value = value;
}

function applyDisplayPercent(percent) {
  app.displayPercent = Math.max(25, Math.min(300, Number(percent)));
  syncDisplaySelect(app.displayPercent);
  const scale = app.displayPercent / 100;
  const root = document.documentElement;
  root.style.setProperty("--lane-height", `${72 * scale}px`);
  root.style.setProperty("--bar-top", `${9 * scale}px`);
  root.style.setProperty("--bar-height", `${54 * scale}px`);
  root.style.setProperty("--bar-line-height", `${52 * scale}px`);
  root.style.setProperty("--bar-font-size", `${Math.max(8, 11 * scale)}px`);
  root.style.setProperty("--machine-font-size", `${Math.max(8, 11 * scale)}px`);
  root.style.setProperty(
    "--pending-font-size",
    `${Math.max(8, 10 * scale)}px`,
  );
  root.style.setProperty(
    "--pending-chip-width",
    `${78 * scale}px`,
  );
  root.style.setProperty(
    "--pending-chip-height",
    `${40 * scale}px`,
  );
  updateVisibleSpan();
  refreshBarStates(app.currentTime);
  renderAxis();
}

function syncAutoJobSubmission(config = {}) {
  elements.autoJobSubmit.checked = Boolean(config.enabled);
}

function syncAutoMachineAnomaly(config = {}) {
  elements.autoMachineAnomaly.checked = Boolean(config.enabled);
}

function renderAxis() {
  while (elements.timeAxis.children.length < 5) {
    const label = document.createElement("span");
    label.className = "axis-label";
    elements.timeAxis.append(label);
  }
  for (let index = 0; index <= 4; index += 1) {
    const label = elements.timeAxis.children[index];
    label.className = `axis-label${index === 2 ? " current" : ""}`;
    label.style.left = `${index * 25}%`;
    const offset = ((index / 4) - 0.5) * app.visibleSpan;
    const timestamp = Math.round(app.currentTime + offset);
    label.textContent = index === 2 ? `T+${timestamp}` : `${timestamp}`;
  }
}

function renderPlayhead() {
  elements.playhead.style.left = "50%";
}

function refreshBarStates(currentTime) {
  for (const [key, bar] of app.bars.entries()) {
    const start = Number(bar.dataset.start);
    const end = Number(bar.dataset.end);
    let stateClass = "";
    if (end <= currentTime) {
      stateClass = "completed";
    } else if (start <= currentTime) {
      stateClass = "running";
    }
    if (stateClass === "completed" && bar.classList.contains("running")) {
      bar.classList.remove("running");
    } else if (stateClass === "running" && bar.classList.contains("completed")) {
      bar.classList.remove("completed");
    } else if (stateClass === "" ) {
      bar.classList.remove("running", "completed");
    }
    if (stateClass && !bar.classList.contains(stateClass)) {
      bar.classList.add(stateClass);
    }
    positionBar(bar);
  }
  refreshTransportSegments(currentTime);
}

function updateMachineStates(states) {
  const orderedStates = [...(states || [])].sort(
    (left, right) => left.id - right.id,
  );
  app.machineStates = orderedStates;
  for (const state of orderedStates) {
    const lane = ensureLane(state.id);
    const statusText =
      state.status === "busy"
        ? "加工"
        : state.status === "scheduled"
          ? "排队"
          : state.status === "failed"
            ? "故障"
            : state.status === "repairing"
              ? "维修"
              : state.status === "degraded"
                ? "降效"
          : "空闲";
    lane.lane.dataset.machineStatus = state.status;
    lane.status.textContent = `${statusText} · ${state.pending}`;
  }
  if (elements.anomalyDialog.open) {
    syncAnomalyMachineAvailability();
  }
}

const MACHINE_STATUS_TEXT = {
  idle: "空闲",
  busy: "加工中",
  scheduled: "排队中",
  failed: "故障",
  repairing: "维修中",
  degraded: "降效运行",
};

function createMachineCard(detection) {
  const card = document.createElement("article");
  card.className = "machine-card";

  const heading = document.createElement("div");
  heading.className = "machine-card-heading";
  const title = document.createElement("h3");
  title.textContent = `检测设备 M${detection.machine_id}`;
  heading.append(title);

  const source = document.createElement("div");
  source.className = "machine-card-source";
  const currentValues = document.createElement("div");
  currentValues.className = "machine-card-current-values";
  const chartNote = document.createElement("div");
  chartNote.className = "machine-chart-note";
  chartNote.textContent = "折线为归一化趋势 · 橙色背景为预警区 · 红色背景为故障区";
  const chartElement = document.createElement("div");
  chartElement.className = "machine-detection-chart";

  card.append(
    heading,
    source,
    currentValues,
    chartNote,
    chartElement,
  );
  const entry = {
    card,
    source,
    currentValues,
    chartElement,
    chart: null,
    detection: null,
  };
  app.machineCards.set(detection.machine_id, entry);
  return entry;
}

function renderMachineDetectionBoard(detections, error = null) {
  if (detections.length === 0) {
    elements.machineBoardSummary.textContent =
      error ? "检测接口不可用" : "暂无设备数据";
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = error || "等待检测数据";
    elements.machineCardGrid.replaceChildren(empty);
    return;
  }

  elements.machineBoardSummary.textContent =
    `数据集设备 ${detections.length} 台 · `
    + `最近 ${detections[0]?.history_points || 0} 个时间点`;

  const fragment = document.createDocumentFragment();
  for (const detection of detections) {
    let entry = app.machineCards.get(detection.machine_id);
    if (!entry) {
      entry = createMachineCard(detection);
    }
    fragment.append(entry.card);
  }
  elements.machineCardGrid.replaceChildren(fragment);
  renderMachineDetectionCharts();
}

function buildDetectionWindows() {
  const detections = [];
  for (const machine of app.detectionMachines) {
    const machineId = Number(machine.machine_id);
    const buffer = app.detectionBuffers.get(machineId) || [];
    if (buffer.length === 0) {
      continue;
    }
    const values = {};
    for (const field of app.detectionFields) {
      values[field.name] = buffer.map(
        (frame) => Number(frame.values?.[field.name] || 0),
      );
    }
    detections.push({
      machine_id: machineId,
      T: Number(buffer.at(-1)?.T || machine.T || 0),
      history_points: buffer.length,
      prediction_horizon: app.detectionPredictionHorizon,
      fields: app.detectionFields,
      timestamps: buffer.map((frame) => Number(frame.t_effective || 0)),
      values,
      label: buffer.map((frame) => Number(frame.label || 0)),
      warn: buffer.map((frame) => Number(frame.warn || 0)),
      wrapped: buffer.map((frame, index) => (
        index > 0
        && Number(frame.t) > Number(buffer[index - 1].t)
        && Number(frame.t_effective)
          < Number(buffer[index - 1].t_effective)
      )),
      source: "overview",
    });
  }
  return detections;
}

function renderDetectionBuffers(error = null) {
  const detections = buildDetectionWindows();
  app.machineDetection.clear();
  for (const detection of detections) {
    app.machineDetection.set(detection.machine_id, detection);
  }
  if (error && detections.length > 0) {
    elements.machineBoardSummary.textContent =
      `数据更新失败，继续显示最近数据：${error}`;
    renderMachineDetectionBoard(detections, null);
    return;
  }
  renderMachineDetectionBoard(detections, error);
}

async function pollDetectionPrediction(timestamp) {
  try {
    const response = await fetch(
      `/api/detection/predict?t=${timestamp}`
      + `&machine_count=${app.detectionMachineCount}`,
      { cache: "no-store" },
    );
    const payload = await response.json();
    if (!response.ok || payload.success === false) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    if (Number(payload.t) !== Number(timestamp)) {
      throw new Error("预测响应时间点与 overview 请求不一致");
    }
    app.detectionPredictionError = null;
  } catch (error) {
    app.detectionPredictionError = error.message;
  }
}

function maybeRequestDetectionPrediction(timestamp) {
  const numericTimestamp = Number(timestamp);
  const interval = Math.max(
    1,
    Number(app.detectionPredictionInterval || 5),
  );
  if (
    !Number.isInteger(numericTimestamp)
    || numericTimestamp % interval !== 0
    || (
      app.detectionLastPredictionT !== null
      && numericTimestamp <= app.detectionLastPredictionT
    )
  ) {
    return;
  }
  app.detectionLastPredictionT = numericTimestamp;
  void pollDetectionPrediction(numericTimestamp);
}

async function pollDetectionOverview() {
  if (app.detectionLoading) {
    return;
  }
  app.detectionLoading = true;
  try {
    const batchSize = Math.max(1, Math.round(Number(app.speed || 1)));
    const requests = Array.from({ length: batchSize }, (_, offset) => {
      const timestamp = app.detectionT + offset;
      return fetch(
        `/api/detection/overview?t=${timestamp}`
        + `&machine_count=${app.detectionMachineCount}`,
        { cache: "no-store" },
      ).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || `HTTP ${response.status}`);
        }
        return payload;
      });
    });
    const settled = await Promise.allSettled(requests);
    const payloads = settled
      .filter((result) => result.status === "fulfilled")
      .map((result) => result.value)
      .sort((left, right) => Number(left.t) - Number(right.t));
    if (payloads.length === 0) {
      const firstError = settled.find(
        (result) => result.status === "rejected",
      );
      throw firstError?.reason || new Error("overview 请求失败");
    }
    if (app.status !== "running") {
      return;
    }
    for (const payload of payloads) {
      const machines = payload.machines || [];
      app.detectionMachines = machines.map((machine) => ({
        machine_id: Number(machine.machine_id),
        T: Number(machine.T || 0),
      }));
      for (const machine of machines) {
        const machineId = Number(machine.machine_id);
        const buffer = app.detectionBuffers.get(machineId) || [];
        buffer.push({
          t: Number(payload.t),
          t_effective: Number(machine.t_effective),
          T: Number(machine.T),
          values: machine.values || {},
          label: Number(machine.label || 0),
          warn: Number(machine.warn || 0),
        });
        if (buffer.length > app.detectionHistoryPoints) {
          buffer.splice(0, buffer.length - app.detectionHistoryPoints);
        }
        app.detectionBuffers.set(machineId, buffer);
      }
      app.detectionPredictionHorizon = Number(
        payload.prediction_horizon || 20,
      );
      maybeRequestDetectionPrediction(payload.t);
    }
    app.detectionT += batchSize;
    app.detectionError = null;
    renderDetectionBuffers();
  } catch (error) {
    app.detectionError = error.message;
    renderDetectionBuffers(app.detectionError);
  } finally {
    app.detectionLoading = false;
  }
}

async function initializeMachineDetection(machineCount) {
  if (app.detectionInitializing) {
    return;
  }
  app.detectionInitializing = true;
  pauseDetectionPolling();
  try {
    const count = Math.max(1, Number(machineCount || 1));
    const metaResponse = await fetch(
      "/api/detection/meta",
      { cache: "no-store" },
    );
    const meta = await metaResponse.json();
    if (!metaResponse.ok) {
      throw new Error(meta.error || `HTTP ${metaResponse.status}`);
    }
    app.detectionFields = meta.selected_features || [];
    app.detectionHistoryPoints = Number(meta.history_points || 60);
    app.detectionPollInterval = Number(meta.poll_interval_ms || 1000);
    app.detectionPredictionInterval = Number(
      meta.prediction_interval || 5,
    );
    app.detectionMachineCount = count;
    app.detectionStreamGeneration = app.generation;
    app.detectionMachines = [];
    app.detectionT = Math.floor(Math.random() * 9000);
    app.detectionLastPredictionT = null;
    app.detectionPredictionError = null;
    app.detectionBuffers.clear();
    for (const entry of app.machineCards.values()) {
      entry.chart?.dispose();
    }
    app.machineCards.clear();
    app.machineDetection.clear();
    renderDetectionBuffers();
    await pollDetectionOverview();
    if (app.detectionTimer !== null) {
      window.clearInterval(app.detectionTimer);
    }
    if (app.status === "running") {
      resumeDetectionPolling();
    }
  } catch (error) {
    app.detectionError = error.message;
    renderDetectionBuffers(app.detectionError);
  } finally {
    app.detectionInitializing = false;
  }
}

function pauseDetectionPolling() {
  if (app.detectionTimer !== null) {
    window.clearInterval(app.detectionTimer);
    app.detectionTimer = null;
  }
}

function clearDetectionStream() {
  pauseDetectionPolling();
  app.detectionStreamGeneration = null;
  app.detectionMachineCount = null;
  app.detectionMachines = [];
  app.detectionLastPredictionT = null;
  app.detectionPredictionError = null;
  app.detectionBuffers.clear();
  for (const entry of app.machineCards.values()) {
    entry.chart?.dispose();
  }
  app.machineCards.clear();
  app.machineDetection.clear();
  renderDetectionBuffers();
}

function resumeDetectionPolling(immediate = false) {
  pauseDetectionPolling();
  if (immediate) {
    void pollDetectionOverview();
  }
  app.detectionTimer = window.setInterval(
    pollDetectionOverview,
    app.detectionPollInterval,
  );
}

function syncDetectionWithSimulation(status) {
  if (status !== "running") {
    pauseDetectionPolling();
    return;
  }
  const selectedDataset = app.datasetCatalog.find(
    (dataset) => dataset.id === elements.datasetSelect.value,
  );
  if (!selectedDataset || app.generation === null) {
    return;
  }
  const machineCount = Number(selectedDataset.num_machines);
  if (
    app.detectionStreamGeneration !== app.generation
    || app.detectionMachineCount !== machineCount
  ) {
    void initializeMachineDetection(machineCount);
    return;
  }
  if (app.detectionTimer === null && !app.detectionInitializing) {
    resumeDetectionPolling(true);
  }
}

function flagRanges(flags, timestamps) {
  const ranges = [];
  let start = null;
  for (let index = 0; index <= flags.length; index += 1) {
    const active = index < flags.length && flags[index];
    if (active && start === null) {
      start = index;
    } else if (!active && start !== null) {
      ranges.push([
        { xAxis: timestamps[start] },
        { xAxis: timestamps[index - 1] },
      ]);
      start = null;
    }
  }
  return ranges;
}

const DETECTION_COLORS = {
  TP2: "#35d6c8",
  TP3: "#6fa8ff",
  H1: "#9b8cff",
  DV_pressure: "#f08ac9",
  Reservoirs: "#c6d95b",
  Oil_temperature: "#ffbd59",
  Motor_current: "#4a9fff",
};

function normalizedSeries(values, field) {
  const minimum = Number(field.min);
  const maximum = Number(field.max);
  if (!Number.isFinite(minimum) || maximum === minimum) {
    return values.map(() => 50);
  }
  return values.map((value) => ((value - minimum) / (maximum - minimum)) * 100);
}

function ensureMachineChart(entry) {
  if (entry.chart || !window.echarts) {
    return entry.chart;
  }
  entry.chart = window.echarts.init(entry.chartElement, null, {
    renderer: "canvas",
  });
  return entry.chart;
}

function renderMachineDetectionCharts() {
  const boardVisible = !elements.machineBoardView.classList.contains("hidden");
  for (const [machineId, entry] of app.machineCards.entries()) {
    const detection = app.machineDetection.get(machineId);
    if (!detection) {
      continue;
    }
    entry.detection = detection;
    const firstTimestamp = detection.timestamps?.[0] ?? "--";
    const lastTimestamp = detection.timestamps?.at(-1) ?? "--";
    const sourceText =
      `流式接口 · T${firstTimestamp}—T${lastTimestamp} · `
      + `${detection.history_points} 个时间点`;
    entry.source.textContent = sourceText;
    entry.source.title = sourceText;
    const continuousFields = (detection.fields || []).filter(
      (field) => field.type === "continuous",
    );
    const currentValue = (field) => (
      detection.values[field.name]?.at(-1) ?? 0
    );
    entry.currentValues.replaceChildren(
      ...continuousFields.map((field) => {
        const item = document.createElement("span");
        const label = document.createElement("span");
        label.textContent = field.label;
        const value = document.createElement("strong");
        value.textContent =
          `${Number(currentValue(field)).toFixed(3)}${field.unit}`;
        item.append(label, value);
        return item;
      }),
    );
    if (!boardVisible) {
      continue;
    }
    const chart = ensureMachineChart(entry);
    if (!chart) {
      entry.chartElement.textContent = "ECharts 未加载";
      continue;
    }
    const slotCount = app.detectionHistoryPoints;
    const slotLabels = Array.from(
      { length: slotCount },
      (_, index) => String(index),
    );
    const padding = Math.max(
      0,
      slotCount - detection.history_points,
    );
    const visibleSlotLabels = slotLabels.slice(padding);
    const warnAreas = flagRanges(
      detection.warn || [],
      visibleSlotLabels,
    ).map((range) => [
      {
        xAxis: range[0].xAxis,
        itemStyle: { color: "rgba(230, 159, 0, 0.1)" },
      },
      { xAxis: range[1].xAxis },
    ]);
    const faultAreas = flagRanges(
      detection.label || [],
      visibleSlotLabels,
    ).map((range) => [
      {
        xAxis: range[0].xAxis,
        itemStyle: { color: "rgba(213, 94, 0, 0.2)" },
      },
      { xAxis: range[1].xAxis },
    ]);
    const series = continuousFields.map((field, index) => {
      const normalized = normalizedSeries(
        detection.values[field.name] || [],
        field,
      );
      for (let pointIndex = 0; pointIndex < normalized.length; pointIndex += 1) {
        if (detection.wrapped?.[pointIndex]) {
          normalized[pointIndex] = null;
        }
      }
      const shifted = [
        ...Array(padding).fill(null),
        ...normalized,
      ];
      return {
        name: field.label,
        type: "line",
        data: shifted,
        showSymbol: false,
        smooth: 0.18,
        lineStyle: {
          width: index === 0 ? 1.8 : 1.4,
          color: DETECTION_COLORS[field.name] || "#8ecbd8",
        },
        emphasis: { focus: "series" },
        markArea: index === 0
          ? {
            silent: true,
            data: [...warnAreas, ...faultAreas],
          }
          : undefined,
      };
    });
    chart.setOption({
      animationDuration: 0,
      animationDurationUpdate: 320,
      animationEasingUpdate: "linear",
      animationThreshold: 5000,
      backgroundColor: "transparent",
      color: Object.values(DETECTION_COLORS),
      legend: {
        top: 1,
        left: 4,
        itemWidth: 10,
        itemHeight: 5,
        textStyle: { color: "#8eaab5", fontSize: 9 },
      },
      grid: { top: 32, right: 8, bottom: 18, left: 8 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(7, 18, 28, 0.96)",
        borderColor: "rgba(120, 178, 194, 0.28)",
        textStyle: { color: "#e9f4f7", fontSize: 10 },
        formatter: (params) => {
          if (!params.length) {
            return "";
          }
          const index = params[0].dataIndex - padding;
          if (index < 0 || index >= detection.timestamps.length) {
            return "";
          }
          const lines = [`T${detection.timestamps[index]}`];
          for (const field of detection.fields) {
            const value = detection.values[field.name][index];
            lines.push(
              `${field.label}: ${Number(value).toFixed(4)}${field.unit}`,
            );
          }
          lines.push(
            `故障标签: ${detection.label[index]}`,
            `预警区: ${detection.warn[index]}`,
          );
          return lines.join("<br>");
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: slotLabels,
        axisLine: { lineStyle: { color: "rgba(120, 178, 194, 0.22)" } },
        axisTick: { show: false },
        axisLabel: {
          color: "#718f9b",
          fontSize: 8,
          interval: 19,
          formatter: (value) => `T${Number(value) - slotCount + 1}`,
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        show: false,
      },
      series,
    }, { notMerge: false, lazyUpdate: false });
  }
}

function resizeMachineCharts() {
  for (const entry of app.machineCards.values()) {
    entry.chart?.resize();
  }
}

function orderStatusDetail(order) {
  const counts = order.status_counts || {};
  return [
    `加工中 ${Number(counts.processing || 0)}`,
    `已完成 ${Number(counts.completed || 0)}`,
    `已取消 ${Number(counts.canceled || 0)}`,
  ].join(" · ");
}

function createOrderCard(order) {
  const details = document.createElement("details");
  details.className = "order-card";
  details.open = false;

  const summary = document.createElement("summary");
  summary.className = "order-card-summary";
  const identity = document.createElement("strong");
  identity.className = "order-identity";
  identity.textContent = order.order_id;
  const source = document.createElement("span");
  source.className = "order-source";
  source.textContent =
    ORDER_SOURCE_TEXT[order.source] || order.source || "订单";
  const status = document.createElement("span");
  status.className = `order-status ${order.status || "processing"}`;
  status.textContent =
    ORDER_STATUS_TEXT[order.status] || order.status || "进行中";
  summary.append(identity, source, status);

  const body = document.createElement("div");
  body.className = "order-card-body";
  const summaryText = document.createElement("div");
  summaryText.className = "order-job-summary";
  summaryText.textContent =
    `${order.job_count || 0} 个作业 · ${orderStatusDetail(order)}`;
  body.append(summaryText);
  for (const jobId of order.job_ids || []) {
    const chip = document.createElement("span");
    chip.className = "order-job-chip";
    chip.textContent = `J${String(jobId).padStart(3, "0")}`;
    body.append(chip);
  }
  details.append(summary, body);
  return details;
}

function renderOrderBatches(orders) {
  const ordered = [...(orders || [])].sort(
    (left, right) => (
      Number(left.submitted_at) - Number(right.submitted_at)
      || String(left.order_id).localeCompare(String(right.order_id))
    ),
  );
  app.orderBatches = ordered;
  elements.orderCount.textContent = `${ordered.length} 单`;
  const signature = JSON.stringify(ordered);
  if (signature === app.orderListSignature) {
    return;
  }
  app.orderListSignature = signature;
  elements.orderList.replaceChildren();
  if (ordered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "等待订单";
    elements.orderList.append(empty);
    return;
  }
  for (const order of ordered) {
    elements.orderList.append(createOrderCard(order));
  }
}

function createJobRow(job) {
  const row = document.createElement("div");
  row.className = `job-row job-${job.status}`;

  const identity = document.createElement("span");
  identity.className = "job-id";
  identity.textContent = `J${String(job.job_id).padStart(3, "0")}`;

  const badge = document.createElement("span");
  badge.className = `job-status-badge ${job.status}`;
  badge.textContent = JOB_STATUS_TEXT[job.status] || job.status;

  const detail = document.createElement("span");
  detail.className = "job-detail";
  const progress =
    `${job.completed_operations}/${job.operation_count} 道`;
  if (job.status === "canceled") {
    const canceledAt = job.canceled_at === null
      ? ""
      : ` · T+${formatTime(job.canceled_at)}`;
    detail.textContent = `${progress}${canceledAt}`;
  } else if (job.status === "completed") {
    const completionTime = job.completion_time === null
      ? ""
      : ` · T+${formatTime(job.completion_time)}`;
    detail.textContent = `${progress}${completionTime}`;
  } else if ((job.current_operations || []).length > 0) {
    const current = job.current_operations[0];
    detail.textContent =
      `O${current.operation_id} · M${current.machine_id} · ${progress}`;
  } else {
    detail.textContent = `等待加工 · ${progress}`;
  }
  row.append(identity, badge, detail);
  return row;
}

function ensureJobGroup(group) {
  if (app.jobGroups.has(group.status)) {
    return app.jobGroups.get(group.status);
  }

  const details = document.createElement("details");
  details.className = `job-group job-group-${group.status}`;
  details.open =
    app.jobGroupOpen[group.status]
    ?? DEFAULT_JOB_GROUP_OPEN[group.status];

  const summary = document.createElement("summary");
  summary.className = "job-group-summary";
  const label = document.createElement("span");
  label.className = "job-group-label";
  label.textContent = JOB_STATUS_TEXT[group.status] || group.label;
  const count = document.createElement("span");
  count.className = "job-group-count";
  count.textContent = "0";
  summary.append(label, count);
  summary.addEventListener("click", () => {
    app.jobGroupOpen[group.status] = !details.open;
  });

  const body = document.createElement("div");
  body.className = "job-group-body";
  details.append(summary, body);
  details.addEventListener("toggle", () => {
    if (details.isConnected) {
      app.jobGroupOpen[group.status] = details.open;
    }
  });
  elements.jobList.append(details);

  const entry = {
    details,
    count,
    body,
    signature: null,
  };
  app.jobGroups.set(group.status, entry);
  return entry;
}

function renderJobStates(states) {
  const orderedStates = [...(states || [])].sort(
    (left, right) => left.job_id - right.job_id,
  );
  app.jobStates = orderedStates;
  elements.jobCount.textContent = String(orderedStates.length);

  for (const group of JOB_GROUPS) {
    const groupJobs = orderedStates.filter(
      (job) => job.status === group.status,
    );
    const entry = ensureJobGroup(group);
    entry.count.textContent = String(groupJobs.length);
    const signature = JSON.stringify(
      groupJobs.map((job) => [
        job.job_id,
        job.status,
        job.operation_count,
        job.completed_operations,
        job.current_operations,
        job.canceled_at,
        job.completion_time,
      ]),
    );
    if (entry.signature === signature) {
      continue;
    }

    entry.body.replaceChildren();
    if (groupJobs.length === 0) {
      const empty = document.createElement("span");
      empty.className = "job-group-empty";
      empty.textContent = "暂无作业";
      entry.body.append(empty);
    } else {
      for (const job of groupJobs) {
        entry.body.append(createJobRow(job));
      }
    }
    entry.signature = signature;
  }
}

function cancelOptionDetail(job) {
  const progress =
    `${job.completed_operations}/${job.operation_count} 道`;
  if (job.status === "canceled") {
    return job.canceled_at === null
      ? progress
      : `${progress} · T+${formatTime(job.canceled_at)} 已取消`;
  }
  if ((job.current_operations || []).length > 0) {
    const current = job.current_operations[0];
    return `O${current.operation_id} · M${current.machine_id} · ${progress}`;
  }
  return `等待加工 · ${progress}`;
}

function appendCancelOrderOptions(orders) {
  const section = document.createElement("section");
  section.className = "cancel-option-group";
  const heading = document.createElement("div");
  heading.className = "cancel-option-heading";
  const headingLabel = document.createElement("span");
  headingLabel.textContent = "订单号";
  const headingCount = document.createElement("span");
  headingCount.textContent = String(orders.length);
  heading.append(headingLabel, headingCount);
  section.append(heading);

  if (orders.length === 0) {
    const empty = document.createElement("div");
    empty.className = "job-group-empty";
    empty.textContent = "暂无订单";
    section.append(empty);
  }
  for (const order of orders) {
    const selectable = order.status !== "canceled";
    const row = document.createElement("label");
    row.className =
      `cancel-option-row${selectable ? "" : " disabled"}`;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = order.order_id;
    checkbox.disabled = !selectable;
    checkbox.className = "cancel-order-checkbox";
    checkbox.dataset.jobIds = JSON.stringify(order.job_ids || []);

    const copy = document.createElement("span");
    copy.className = "cancel-option-copy";
    const identity = document.createElement("strong");
    identity.textContent = order.order_id;
    const detail = document.createElement("span");
    detail.textContent =
      `${order.job_count || 0} 个作业 · ${orderStatusDetail(order)}`;
    copy.append(identity, detail);

    const state = document.createElement("span");
    state.className = "cancel-option-state";
    state.textContent = selectable
      ? ORDER_STATUS_TEXT[order.status] || order.status
      : "不可重复取消";
    row.append(checkbox, copy, state);
    section.append(row);
  }
  elements.cancelOrderOptions.append(section);
}

function appendCancelOptionGroup(label, jobs, selectable) {
  const section = document.createElement("section");
  section.className = "cancel-option-group";
  const heading = document.createElement("div");
  heading.className = "cancel-option-heading";
  const headingLabel = document.createElement("span");
  headingLabel.textContent = label;
  const headingCount = document.createElement("span");
  headingCount.textContent = String(jobs.length);
  heading.append(headingLabel, headingCount);
  section.append(heading);

  if (jobs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "job-group-empty";
    empty.textContent = "暂无作业";
    section.append(empty);
  }
  for (const job of jobs) {
    const row = document.createElement("label");
    row.className =
      `cancel-option-row${selectable ? "" : " disabled"}`;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = String(job.job_id);
    checkbox.disabled = !selectable;
    checkbox.className = "cancel-job-checkbox";

    const copy = document.createElement("span");
    copy.className = "cancel-option-copy";
    const identity = document.createElement("strong");
    identity.textContent = `J${String(job.job_id).padStart(3, "0")}`;
    const detail = document.createElement("span");
    detail.textContent = cancelOptionDetail(job);
    copy.append(identity, detail);

    const state = document.createElement("span");
    state.className = "cancel-option-state";
    state.textContent = selectable
      ? JOB_STATUS_TEXT[job.status] || job.status
      : "不可重复取消";
    row.append(checkbox, copy, state);
    section.append(row);
  }
  elements.cancelJobOptions.append(section);
}

function selectedCancelJobIds() {
  return [
    ...elements.cancelJobOptions.querySelectorAll(
      ".cancel-job-checkbox:not(:disabled):checked",
    ),
  ].map((checkbox) => Number(checkbox.value));
}

function selectedCancelOrderIds() {
  return [
    ...elements.cancelOrderOptions.querySelectorAll(
      ".cancel-order-checkbox:not(:disabled):checked",
    ),
  ].map((checkbox) => checkbox.value);
}

function syncJobCheckboxesFromOrder(orderCheckbox) {
  const jobIds = JSON.parse(orderCheckbox.dataset.jobIds || "[]");
  for (const jobId of jobIds) {
    const jobCheckbox = elements.cancelJobOptions.querySelector(
      `.cancel-job-checkbox[value="${Number(jobId)}"]`,
    );
    if (jobCheckbox && !jobCheckbox.disabled) {
      jobCheckbox.checked = orderCheckbox.checked;
    }
  }
}

function syncOrderCheckboxStates() {
  for (const orderCheckbox of elements.cancelOrderOptions.querySelectorAll(
    ".cancel-order-checkbox:not(:disabled)",
  )) {
    const jobIds = JSON.parse(orderCheckbox.dataset.jobIds || "[]");
    const jobCheckboxes = jobIds
      .map((jobId) => elements.cancelJobOptions.querySelector(
        `.cancel-job-checkbox[value="${Number(jobId)}"]:not(:disabled)`,
      ))
      .filter(Boolean);
    if (jobCheckboxes.length === 0) {
      orderCheckbox.checked = false;
      orderCheckbox.indeterminate = false;
      continue;
    }
    const selectedCount = jobCheckboxes.filter(
      (checkbox) => checkbox.checked,
    ).length;
    orderCheckbox.checked = selectedCount === jobCheckboxes.length;
    orderCheckbox.indeterminate =
      selectedCount > 0 && selectedCount < jobCheckboxes.length;
  }
}

function updateCancelSelection() {
  syncOrderCheckboxStates();
  const selectedJobs = selectedCancelJobIds();
  const selectedOrders = selectedCancelOrderIds();
  const selectable = [
    ...elements.cancelJobOptions.querySelectorAll(
      ".cancel-job-checkbox:not(:disabled)",
    ),
  ];
  elements.cancelSelectionCount.textContent =
    `已选 ${selectedOrders.length} 个订单，${selectedJobs.length} 个作业`;
  elements.cancelSelectAll.checked =
    selectable.length > 0
    && selectedJobs.length === selectable.length;
  elements.cancelSelectAll.indeterminate =
    selectedJobs.length > 0 && selectedJobs.length < selectable.length;
  elements.confirmCancelJobs.disabled =
    app.cancelRequestPending
    || (selectedJobs.length === 0 && selectedOrders.length === 0)
    || app.status !== "running";
}

function openCancelDialog() {
  const processingJobs = app.jobStates.filter(
    (job) => job.status === "processing",
  );
  const completedJobs = app.jobStates.filter(
    (job) => job.status === "completed",
  );
  const canceledJobs = app.jobStates.filter(
    (job) => job.status === "canceled",
  );
  elements.cancelOrderOptions.replaceChildren();
  elements.cancelJobOptions.replaceChildren();
  appendCancelOrderOptions(app.orderBatches);
  appendCancelOptionGroup(
    "加工中作业",
    processingJobs,
    true,
  );
  appendCancelOptionGroup(
    "已完成作业",
    completedJobs,
    true,
  );
  appendCancelOptionGroup(
    "已取消作业",
    canceledJobs,
    false,
  );
  elements.cancelSelectAll.checked = false;
  elements.cancelSelectAll.indeterminate = false;
  elements.cancelSelectAll.disabled =
    processingJobs.length + completedJobs.length === 0
    && !app.orderBatches.some((order) => order.status !== "canceled");
  app.cancelRequestPending = false;
  updateCancelSelection();
  elements.cancelJobsDialog.showModal();
}

async function confirmCancelJobs() {
  if (app.cancelRequestPending) {
    return;
  }
  const jobIds = selectedCancelJobIds();
  const orderIds = selectedCancelOrderIds();
  if (jobIds.length === 0 && orderIds.length === 0) {
    return;
  }
  app.cancelRequestPending = true;
  updateCancelSelection();
  elements.confirmCancelJobs.textContent = "取消中...";
  try {
    const response = await fetch("/api/jobs/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_ids: jobIds,
        order_ids: orderIds,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    elements.cancelJobsDialog.close();
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `批量取消订单失败：${error.message}`;
  } finally {
    app.cancelRequestPending = false;
    elements.confirmCancelJobs.textContent = "确认取消";
    updateCancelSelection();
  }
}

function createPendingChip(operation) {
  const chip = document.createElement("span");
  chip.className = "pending-chip";
  chip.dataset.pendingKey = operationKey(
    operation.job_id,
    operation.operation_id,
  );
  chip.style.setProperty("--chip-hue", jobHue(operation.job_id));
  chip.textContent = `J${operation.job_id}-O${operation.operation_id}`;
  updatePendingChip(chip, operation);
  return chip;
}

function updatePendingChip(chip, operation) {
  chip.title =
    `待加工：作业 ${operation.job_id} / 工序 ${operation.operation_id} / `
    + `计划 ${operation.start_time}-${operation.end_time}`;
}

function replayPendingAnimation(chip, className, delay) {
  chip.classList.remove("pending-shift", "pending-enter");
  void chip.offsetWidth;
  chip.style.animationDelay = `${delay}ms`;
  chip.classList.add(className);
}

function addPendingLeaveAnimation(chip, queue) {
  const queueRect = queue.getBoundingClientRect();
  const chipRect = chip.getBoundingClientRect();
  const ghost = chip.cloneNode(true);
  ghost.classList.remove("pending-shift", "pending-enter");
  ghost.classList.add("pending-leaving");
  ghost.style.left = `${chipRect.left - queueRect.left}px`;
  ghost.style.top = `${chipRect.top - queueRect.top}px`;
  ghost.style.width = `${chipRect.width}px`;
  ghost.style.height = `${chipRect.height}px`;
  queue.append(ghost);
  window.setTimeout(() => ghost.remove(), 340);
}

function renderPendingQueues(plan, currentTime) {
  const queues = new Map();
  const activePlan = (
    app.status === "finished" || app.status === "failed"
  )
    ? []
    : plan || [];
  for (const operation of activePlan) {
    const isWaiting = (
      operation.status === "pending"
      || operation.status === "scheduled"
    );
    const hasStatus = (
      operation.status === "pending"
      || operation.status === "scheduled"
      || operation.status === "processing"
      || operation.status === "completed"
      || operation.status === "canceled"
    );
    if (
      (hasStatus && !isWaiting)
      || (!hasStatus && operation.start_time <= currentTime)
    ) {
      continue;
    }
    if (!queues.has(operation.machine_id)) {
      queues.set(operation.machine_id, []);
    }
    queues.get(operation.machine_id).push(operation);
  }

  for (const [machineId, lane] of app.lanes.entries()) {
    const pending = (queues.get(machineId) || []).sort(
      (left, right) => left.start_time - right.start_time,
    );
    const railWidth = lane.pendingQueue.clientWidth || 420;
    const signature = pending
      .map((operation) => {
        const key = operationKey(
          operation.job_id,
          operation.operation_id,
        );
        return [
          key,
          operation.start_time,
          operation.end_time,
          operation.transport_start,
          operation.transport_end,
          operation.status,
        ].join(":");
      })
      .concat(`@${app.displayPercent}@${railWidth}`)
      .join("|");
    if (app.pendingSignatures.get(machineId) === signature) {
      continue;
    }

    const chipWidth = 78 * (app.displayPercent / 100) + 6;
    const visibleCount = Math.max(
      1,
      Math.min(8, Math.floor((railWidth - 24) / chipWidth)),
    );
    const visibleOperations = pending.slice(0, visibleCount);
    const visibleKeys = visibleOperations.map((operation) =>
      operationKey(operation.job_id, operation.operation_id)
    );
    const desiredKeys = new Set(visibleKeys);
    const oldChips = [
      ...lane.pendingQueue.querySelectorAll(
        ".pending-chip:not(.pending-leaving)",
      ),
    ];
    const oldIndexes = new Map(
      oldChips.map((chip, index) => [chip.dataset.pendingKey, index]),
    );
    const chipByKey = new Map(
      oldChips.map((chip) => [chip.dataset.pendingKey, chip]),
    );

    lane.pendingQueue
      .querySelectorAll(".pending-more, .pending-empty")
      .forEach((element) => element.remove());

    for (const chip of oldChips) {
      if (!desiredKeys.has(chip.dataset.pendingKey)) {
        addPendingLeaveAnimation(chip, lane.pendingQueue);
        chip.remove();
      }
    }

    visibleOperations.forEach((operation, index) => {
      const key = visibleKeys[index];
      let chip = chipByKey.get(key);
      const isNewChip = chip === undefined;
      if (isNewChip) {
        chip = createPendingChip(operation);
      } else {
        updatePendingChip(chip, operation);
      }
      lane.pendingQueue.append(chip);

      if (isNewChip) {
        replayPendingAnimation(chip, "pending-enter", index * 55);
      } else {
        const previousIndex = oldIndexes.get(key);
        if (previousIndex > index) {
          replayPendingAnimation(
            chip,
            "pending-shift",
            index * 45,
          );
        }
      }
    });

    if (visibleOperations.length === 0) {
      const empty = document.createElement("span");
      empty.className = "pending-empty";
      empty.textContent = "—";
      lane.pendingQueue.append(empty);
    } else if (pending.length > visibleCount) {
      const more = document.createElement("span");
      more.className = "pending-more";
      more.textContent = `+${pending.length - visibleCount}`;
      lane.pendingQueue.append(more);
    }
    app.pendingSignatures.set(machineId, signature);
  }
}

function eventDescription(event) {
  if (event.order_ids?.length) {
    return `订单 ${event.order_ids.join("、")} / 作业 ${event.job_ids?.join("、") || "-"}`;
  }
  if (event.order_id) {
    return `订单 ${event.order_id} / 作业 ${event.job_ids?.join("、") || "-"}`;
  }
  if (event.job_ids?.length) {
    return `作业 ${event.job_ids.join("、")}`;
  }
  if (event.job_id !== undefined && event.operation_id !== undefined) {
    return `作业 ${event.job_id} / 工序 ${event.operation_id} / M${event.machine_id ?? "-"}`;
  }
  if (event.machine_id !== undefined && event.anomaly_type) {
    return `机器 M${event.machine_id} / ${event.anomaly_type}`;
  }
  if (event.machine_id !== undefined) {
    return `机器 M${event.machine_id}`;
  }
  return "";
}

function addAnomalyEvent(event) {
  const empty = elements.anomalyList.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  const row = document.createElement("div");
  row.className = "event-row";
  const typeLabel = EVENT_TEXT[event.type] || event.type;
  row.innerHTML = `
    <span class="event-time">T+${formatTime(event.timestamp)}</span>
    <i class="event-dot"></i>
    <div class="event-copy">
      <strong>${escapeHtml(typeLabel)}</strong>
      <span>${escapeHtml(eventDescription(event))}</span>
    </div>
  `;
  elements.anomalyList.prepend(row);
  while (elements.anomalyList.children.length > 320) {
    elements.anomalyList.lastElementChild.remove();
  }

  app.anomalyCount += 1;
  elements.anomalyCount.textContent = app.anomalyCount;
}

function handleOperationEvent(event) {
  if (
    event.type !== "OperationStartEvent"
    && event.type !== "OperationFinishEvent"
  ) {
    return;
  }

  const key = operationKey(event.job_id, event.operation_id);
  let bar = app.bars.get(key);
  if (!bar) {
    bar = ensureBar({
      job_id: event.job_id,
      operation_id: event.operation_id,
      machine_id: event.machine_id,
      start_time: event.timestamp,
      end_time: event.timestamp + (event.processing_time || 0),
    });
  }

  if (event.type === "OperationStartEvent") {
    bar.dataset.start = event.timestamp;
    bar.dataset.end = event.timestamp + (event.processing_time || 0);
    bar.classList.remove("entering-current");
    void bar.offsetWidth;
    bar.classList.add("entering-current");
    window.setTimeout(
      () => bar.classList.remove("entering-current"),
      540,
    );
  } else {
    bar.dataset.end = event.timestamp;
  }
}

function setStatus(status) {
  app.status = status;
  elements.connectionStatus.className = `status-pill ${status}`;
  elements.connectionStatus.textContent = STATUS_TEXT[status] || status;
  elements.startButton.disabled =
    !app.datasetsReady
    || status === "running"
    || status === "paused"
    || status === "preparing"
    || status === "reoptimizing";
  elements.datasetSelect.disabled =
    status === "running"
    || status === "paused"
    || status === "preparing"
    || status === "reoptimizing";
  elements.reoptimizerSelect.disabled = status !== "running";
  elements.reoptimizeButton.disabled = status !== "running";
  elements.insertAnomalyButton.disabled = status !== "running";
  elements.manualJobInsertButton.disabled = status !== "running";
  elements.cancelJobsButton.disabled = status !== "running";
  elements.pauseButton.disabled =
    status !== "running" && status !== "paused";
  elements.stopButton.disabled =
    status !== "running"
    && status !== "paused"
    && status !== "reoptimizing";
  elements.pauseButton.textContent =
    status === "paused" ? "继续仿真" : "暂停仿真";
  updateReoptimizeButtonText();
  elements.startButton.textContent =
    ["finished", "stopped"].includes(status) ? "再次启动" : "启动仿真";
  if (elements.cancelJobsDialog.open) {
    updateCancelSelection();
  }
  syncDetectionWithSimulation(status);
}

const REOPTIMIZERS = {
  mofjsp: {
    endpoint: "/api/reoptimize",
    label: "DRL",
    buttonLabel: "DRL 重调度",
    busyLabel: "DRL 重调度中...",
    payload: { num_samples: 1, seed: 0 },
  },
  hls: {
    endpoint: "/api/hls-reoptimize",
    label: "HLS",
    buttonLabel: "HLS 重调度",
    busyLabel: "HLS 重调度中...",
    payload: { seed: 0 },
  },
};

function selectedReoptimizer() {
  return REOPTIMIZERS[elements.reoptimizerSelect.value]
    || REOPTIMIZERS.mofjsp;
}

function updateReoptimizeButtonText() {
  if (app.status === "reoptimizing") {
    return;
  }
  elements.reoptimizeButton.textContent =
    selectedReoptimizer().buttonLabel;
}

async function reoptimizeWithSelectedMethod() {
  const optimizer = selectedReoptimizer();
  elements.reoptimizeButton.disabled = true;
  elements.reoptimizerSelect.disabled = true;
  elements.reoptimizeButton.textContent = optimizer.busyLabel;
  try {
    const response = await fetch(optimizer.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(optimizer.payload),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `${optimizer.label}重调度失败：${error.message}`;
  } finally {
    updateReoptimizeButtonText();
    elements.reoptimizeButton.disabled = app.status !== "running";
    elements.reoptimizerSelect.disabled = app.status !== "running";
  }
}

function syncSpeedSelect(speed) {
  const value = String(normalizeWebSpeed(speed));
  elements.speedSelect.value = value;
}

function normalizeWebSpeed(speed) {
  const numericSpeed = Number(speed);
  return [1, 2, 5].includes(numericSpeed) ? numericSpeed : 5;
}

function applySnapshot(snapshot) {
  if (app.generation !== null && app.generation !== snapshot.generation) {
    resetView();
  }
  app.generation = snapshot.generation;
  if (snapshot.selected_dataset?.id) {
    elements.datasetSelect.value = snapshot.selected_dataset.id;
  }
  app.speed = normalizeWebSpeed(snapshot.speed);
  const serverTime = Number(snapshot.current_time || 0);
  if (
    snapshot.status === "running"
    || snapshot.status === "reoptimizing"
  ) {
    app.currentTime = Math.max(app.currentTime, serverTime);
  } else {
    app.currentTime = serverTime;
  }
  app.serverTime = serverTime;
  app.lastServerTime = app.currentTime;
  app.lastSyncAt = performance.now();
  syncSpeedSelect(snapshot.speed);
  const displayPercent = Number(snapshot.display_percent || 100);
  if (app.displayPercent !== displayPercent) {
    applyDisplayPercent(displayPercent);
  }

  updateHorizon(Number(snapshot.horizon || 100));
  if (app.planRevision !== snapshot.plan_revision) {
    app.planRevision = snapshot.plan_revision;
    renderPlan(snapshot.plan);
  }
  renderAxis();
  renderOrderBatches(snapshot.order_batches);
  renderJobStates(snapshot.job_states);
  updateMachineStates(snapshot.machine_states);

  for (const event of snapshot.events) {
    handleOperationEvent(event);
    if (ANOMALY_LIST_EVENT_TYPES.has(event.type)) {
      addAnomalyEvent(event);
    }
  }
  app.after = snapshot.next_event_index;

  elements.currentTime.textContent = formatTime(app.currentTime);
  elements.clockReadout.textContent = `T+${String(Math.round(app.currentTime)).padStart(4, "0")}`;
  elements.makespan.textContent = snapshot.makespan || "--";
  elements.finishedJobs.textContent = `${snapshot.finished_jobs} / ${snapshot.total_jobs}`;
  elements.totalEnergy.textContent =
    snapshot.objectives?.energy === undefined
      ? "--"
      : String(Math.round(Number(snapshot.objectives.energy)));
  elements.deliveryPenalty.textContent =
    snapshot.objectives?.penalty === undefined
      ? "--"
      : String(Math.round(Number(snapshot.objectives.penalty)));
  setStatus(snapshot.status);
  refreshBarStates(app.currentTime);
  renderPendingQueues(snapshot.plan, app.serverTime);
  renderPlayhead();
  syncAutoJobSubmission(snapshot.auto_job_submission);
  syncAutoMachineAnomaly(snapshot.auto_machine_anomaly);

  elements.errorBanner.classList.toggle("hidden", !snapshot.error);
  if (snapshot.error) {
    elements.errorBanner.textContent = snapshot.error;
  }
}

async function poll() {
  try {
    const response = await fetch(`/api/state?after=${app.after}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    applySnapshot(await response.json());
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `无法连接仿真服务：${error.message}`;
  } finally {
    if (!["finished", "failed", "stopped"].includes(app.status)) {
      pollTimer = window.setTimeout(poll, 200);
    }
  }
}

async function startSimulation() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
  }
  resetView();
  app.datasetsReady = true;
  elements.startButton.disabled = true;
  const datasetId = elements.datasetSelect.value;
  if (!datasetId) {
    elements.startButton.disabled = false;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = "请先选择数据源。";
    return;
  }
  try {
    const response = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    setStatus(result.status);
    pollTimer = window.setTimeout(poll, 100);
  } catch (error) {
    elements.startButton.disabled = false;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `启动仿真失败：${error.message}`;
  }
}

async function loadDatasets() {
  try {
    const response = await fetch("/api/datasets", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    app.datasetCatalog = result.datasets || [];
    elements.datasetSelect.replaceChildren();
    for (const dataset of result.datasets) {
      const option = document.createElement("option");
      option.value = dataset.id;
      option.textContent = dataset.label;
      option.title = dataset.id;
      option.selected = dataset.id === result.default_dataset;
      elements.datasetSelect.append(option);
    }
    app.datasetsReady = true;
    setStatus(app.status);
    poll();
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `读取数据源失败：${error.message}`;
  }
}

async function changeSpeed() {
  const speed = Number(elements.speedSelect.value);
  try {
    const response = await fetch("/api/speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speed }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    app.speed = speed;
    app.lastServerTime = app.currentTime;
    app.lastSyncAt = performance.now();
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `调整倍速失败：${error.message}`;
  }
}

async function togglePause() {
  if (app.status !== "running" && app.status !== "paused") {
    return;
  }
  const paused = app.status === "running";
  elements.pauseButton.disabled = true;
  elements.pauseButton.textContent =
    paused ? "暂停中..." : "恢复中...";
  try {
    const response = await fetch("/api/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    setStatus(result.status);
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `${paused ? "暂停" : "继续"}仿真失败：${error.message}`;
    setStatus(app.status);
  }
}

async function stopSimulation() {
  if (
    app.status !== "running"
    && app.status !== "paused"
    && app.status !== "reoptimizing"
  ) {
    return;
  }
  elements.stopButton.disabled = true;
  elements.stopButton.textContent = "停止中...";
  try {
    const response = await fetch("/api/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    setStatus(result.status);
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `停止仿真失败：${error.message}`;
    setStatus(app.status);
  } finally {
    elements.stopButton.textContent = "停止仿真";
  }
}

async function changeAutoJobSubmission() {
  const enabled = elements.autoJobSubmit.checked;
  try {
    const response = await fetch("/api/auto-job-submission", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    syncAutoJobSubmission(result.auto_job_submission);
  } catch (error) {
    elements.autoJobSubmit.checked = !enabled;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `设置自动插单失败：${error.message}`;
  }
}

async function changeAutoMachineAnomaly() {
  const enabled = elements.autoMachineAnomaly.checked;
  try {
    const response = await fetch("/api/auto-machine-anomaly", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    syncAutoMachineAnomaly(result.auto_machine_anomaly);
  } catch (error) {
    elements.autoMachineAnomaly.checked = !enabled;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `设置自动插入异常失败：${error.message}`;
  }
}

async function insertJobsManually() {
  elements.manualJobInsertButton.disabled = true;
  elements.manualJobInsertButton.textContent = "插单中...";
  try {
    const response = await fetch("/api/jobs/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seed: Math.floor(Math.random() * 1_000_000_000),
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `手动插单失败：${error.message}`;
  } finally {
    elements.manualJobInsertButton.textContent = "手动插单";
    elements.manualJobInsertButton.disabled = app.status !== "running";
  }
}

function populateAnomalyMachines() {
  const selectedValue = elements.anomalyMachineSelect.value;
  elements.anomalyMachineSelect.replaceChildren();
  for (const machine of app.machineStates) {
    const option = document.createElement("option");
    option.value = String(machine.id);
    option.textContent = `M${machine.id}`;
    option.disabled = machine.status === "failed"
      || machine.status === "repairing";
    elements.anomalyMachineSelect.append(option);
  }

  const options = [...elements.anomalyMachineSelect.options];
  const preferred = options.find(
    (option) => option.value === selectedValue && !option.disabled,
  ) || options.find((option) => !option.disabled);
  if (preferred) {
    elements.anomalyMachineSelect.value = preferred.value;
  }
  elements.confirmAnomaly.disabled = !preferred;
}

function syncAnomalyMachineAvailability() {
  const machineById = new Map(
    app.machineStates.map((machine) => [String(machine.id), machine]),
  );
  for (const option of elements.anomalyMachineSelect.options) {
    const machine = machineById.get(option.value);
    option.disabled = !machine
      || machine.status === "failed"
      || machine.status === "repairing";
  }
  const selected = elements.anomalyMachineSelect.selectedOptions[0];
  if (!selected || selected.disabled) {
    const available = [...elements.anomalyMachineSelect.options].find(
      (option) => !option.disabled,
    );
    if (available) {
      elements.anomalyMachineSelect.value = available.value;
    }
  }
  elements.confirmAnomaly.disabled =
    !elements.anomalyMachineSelect.selectedOptions[0]
    || elements.anomalyMachineSelect.selectedOptions[0].disabled;
}

function openAnomalyDialog() {
  if (app.status !== "running") {
    return;
  }
  populateAnomalyMachines();
  updateAnomalyDurationDefault();
  elements.anomalyDialog.showModal();
}

function updateAnomalyDurationDefault() {
  const option = elements.anomalyTypeSelect.selectedOptions[0];
  if (option?.dataset.duration) {
    const minimum = Number(option.dataset.min || 1);
    const maximum = Number(option.dataset.max || 60);
    elements.anomalyDuration.min = String(minimum);
    elements.anomalyDuration.max = String(maximum);
    elements.anomalyDuration.step = "1";
    elements.anomalyDuration.value = option.dataset.duration;
    elements.anomalyDurationHint.textContent =
      `可选范围：${minimum}–${maximum}，`
      + `默认持续时间：${option.dataset.duration}`;
  }
}

async function insertMachineAnomaly() {
  const machineId = Number(elements.anomalyMachineSelect.value);
  const anomalyType = elements.anomalyTypeSelect.value;
  const duration = Number(elements.anomalyDuration.value);
  const minimum = Number(elements.anomalyDuration.min);
  const maximum = Number(elements.anomalyDuration.max);
  if (
    !Number.isFinite(machineId)
    || !anomalyType
    || !Number.isInteger(duration)
    || !Number.isFinite(minimum)
    || !Number.isFinite(maximum)
    || duration < minimum
    || duration > maximum
  ) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `持续时间必须是 ${minimum}–${maximum} 之间的整数。`;
    return;
  }

  elements.confirmAnomaly.disabled = true;
  elements.confirmAnomaly.textContent = "插入中...";
  try {
    const response = await fetch("/api/anomalies/machine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        machine_id: machineId,
        anomaly_type: anomalyType,
        duration,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    elements.anomalyDialog.close();
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `插入设备异常失败：${error.message}`;
  } finally {
    elements.confirmAnomaly.textContent = "插入异常";
    if (elements.anomalyDialog.open) {
      syncAnomalyMachineAvailability();
    }
  }
}

function animateTimeline(now) {
  if (app.status === "running" && now - app.lastFrameRenderAt >= 16) {
    const estimatedTime =
      app.lastServerTime
      + ((now - app.lastSyncAt) / 1000) * app.speed;
    if (estimatedTime > app.currentTime) {
      app.currentTime = estimatedTime;
      elements.currentTime.textContent = formatTime(app.currentTime);
      elements.clockReadout.textContent =
        `T+${String(Math.round(app.currentTime)).padStart(4, "0")}`;
      refreshBarStates(app.currentTime);
      if (now - app.lastAxisRenderAt >= 100) {
        renderAxis();
        app.lastAxisRenderAt = now;
      }
    }
    app.lastFrameRenderAt = now;
  }
  window.requestAnimationFrame(animateTimeline);
}

async function changeDisplayPercent() {
  const displayPercent = Number(elements.displaySelect.value);
  applyDisplayPercent(displayPercent);
  try {
    const response = await fetch("/api/display-percent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_percent: displayPercent }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `调整显示比例失败：${error.message}`;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

renderAxis();
setStatus("idle");
elements.scheduleTab.addEventListener(
  "click",
  () => setDashboardTab("schedule"),
);
elements.machineBoardTab.addEventListener(
  "click",
  () => setDashboardTab("machine-board"),
);
elements.startButton.addEventListener("click", startSimulation);
elements.autoJobSubmit.addEventListener(
  "change",
  changeAutoJobSubmission,
);
elements.autoMachineAnomaly.addEventListener(
  "change",
  changeAutoMachineAnomaly,
);
elements.manualJobInsertButton.addEventListener(
  "click",
  insertJobsManually,
);
elements.insertAnomalyButton.addEventListener("click", openAnomalyDialog);
elements.anomalyDialogClose.addEventListener(
  "click",
  () => elements.anomalyDialog.close(),
);
elements.anomalyDialogDismiss.addEventListener(
  "click",
  () => elements.anomalyDialog.close(),
);
elements.anomalyTypeSelect.addEventListener(
  "change",
  updateAnomalyDurationDefault,
);
elements.confirmAnomaly.addEventListener(
  "click",
  insertMachineAnomaly,
);
elements.cancelJobsButton.addEventListener("click", openCancelDialog);
elements.cancelDialogClose.addEventListener(
  "click",
  () => elements.cancelJobsDialog.close(),
);
elements.cancelDialogDismiss.addEventListener(
  "click",
  () => elements.cancelJobsDialog.close(),
);
elements.cancelSelectAll.addEventListener("change", () => {
  for (const checkbox of elements.cancelOrderOptions.querySelectorAll(
    ".cancel-order-checkbox:not(:disabled)",
  )) {
    checkbox.checked = elements.cancelSelectAll.checked;
  }
  for (const checkbox of elements.cancelJobOptions.querySelectorAll(
    ".cancel-job-checkbox:not(:disabled)",
  )) {
    checkbox.checked = elements.cancelSelectAll.checked;
  }
  updateCancelSelection();
});
elements.cancelOrderOptions.addEventListener("change", (event) => {
  if (event.target.classList.contains("cancel-order-checkbox")) {
    syncJobCheckboxesFromOrder(event.target);
  }
  updateCancelSelection();
});
elements.cancelJobOptions.addEventListener(
  "change",
  updateCancelSelection,
);
elements.confirmCancelJobs.addEventListener(
  "click",
  confirmCancelJobs,
);
elements.pauseButton.addEventListener("click", togglePause);
elements.stopButton.addEventListener("click", stopSimulation);
elements.reoptimizeButton.addEventListener(
  "click",
  reoptimizeWithSelectedMethod,
);
elements.reoptimizerSelect.addEventListener(
  "change",
  updateReoptimizeButtonText,
);
elements.datasetSelect.addEventListener("change", () => {
  clearDetectionStream();
});
elements.speedSelect.addEventListener("change", changeSpeed);
elements.displaySelect.addEventListener("change", changeDisplayPercent);
window.addEventListener("resize", resizeMachineCharts);
elements.timelineBody.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "PageDown") {
    event.preventDefault();
    elements.timelineBody.scrollBy({
      top: elements.timelineBody.clientHeight * 0.8,
      behavior: "smooth",
    });
  } else if (event.key === "ArrowUp" || event.key === "PageUp") {
    event.preventDefault();
    elements.timelineBody.scrollBy({
      top: -elements.timelineBody.clientHeight * 0.8,
      behavior: "smooth",
    });
  }
});
enableTimelineWheelScroll();
window.requestAnimationFrame(animateTimeline);
loadDatasets();
