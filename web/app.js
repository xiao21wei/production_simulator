const STATUS_TEXT = {
  idle: "等待启动",
  preparing: "准备数据",
  running: "运行中",
  paused: "已暂停",
  reoptimizing: "重调度中 · 已暂停",
  animating: "队列调整动画 · 已暂停",
  stopping: "正在停止",
  stopped: "已停止",
  finished: "已完成",
  failed: "运行失败",
};

const MACHINE_ANOMALY_BADGE_TEXT = {
  short_failure: "短故障",
  medium_failure: "中故障",
  long_failure: "长故障",
  degraded: "降额",
};

const EVENT_TEXT = {
  OperationStartEvent: "工序开始",
  OperationFinishEvent: "工序完成",
  TransportFinishEvent: "运输完成",
  ProcessStageBatchScheduleEvent: "工艺批量排程",
  JobSubmitEvent: "作业提交",
  JobStartEvent: "作业开始",
  JobFinishEvent: "作业完成",
  ScheduleEvent: "生成排程",
  OrderInsertEvent: "插单",
  OrderCancelEvent: "订单取消",
  MachineAnomalyEvent: "设备异常",
  MachineRecoveryEvent: "设备恢复",
  MaterialReplenishmentEvent: "物料异常 · 补料",
  MaterialRecoveryEvent: "物料异常 · 恢复",
};

const ANOMALY_LIST_EVENT_TYPES = new Set([
  "OrderInsertEvent",
  "OrderCancelEvent",
  "MachineAnomalyEvent",
  "MachineRecoveryEvent",
  "MaterialReplenishmentEvent",
  "MaterialRecoveryEvent",
]);

const MATERIAL_ANOMALY_EVENT_TYPES = new Set([
  "MaterialReplenishmentEvent",
  "MaterialRecoveryEvent",
]);

const TIMELINE_REBUILD_EVENT_TYPES = new Set([
  "MachineAnomalyEvent",
  "MachineRecoveryEvent",
]);

const JOB_STATUS_TEXT = {
  processing: "加工中",
  completed: "已完成",
  canceled: "已取消",
};

const PROCESS_ACTIVE_STATUS_TEXT = {
  1: "冲压中",
  2: "焊装中",
  3: "涂装中",
  4: "总装中",
};

const JOB_GROUPS = [
  {
    key: "stage-1",
    status: "processing",
    stage: 1,
    label: "冲压中",
    className: "processing",
  },
  {
    key: "stage-2",
    status: "processing",
    stage: 2,
    label: "焊装中",
    className: "processing",
  },
  {
    key: "stage-3",
    status: "processing",
    stage: 3,
    label: "涂装中",
    className: "processing",
  },
  {
    key: "stage-4",
    status: "processing",
    stage: 4,
    label: "总装中",
    className: "processing",
  },
  {
    key: "completed",
    status: "completed",
    label: "已完成",
    className: "completed",
  },
  {
    key: "canceled",
    status: "canceled",
    label: "已取消",
    className: "canceled",
  },
];

const TIMELINE_OPERATION_STATUSES = new Set([
  "processing",
  "completed",
]);

const DEFAULT_JOB_GROUP_OPEN = {
  "stage-1": false,
  "stage-2": false,
  "stage-3": false,
  "stage-4": false,
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
  materialBoardGrid: document.querySelector("#material-board-grid"),
  materialBoardSummary: document.querySelector("#material-board-summary"),
  materialBoardTab: document.querySelector("#material-board-tab"),
  materialBoardView: document.querySelector("#material-board-view"),
  anomalyModelTab: document.querySelector("#anomaly-model-tab"),
  anomalyModelPanel: document.querySelector("#anomaly-model-panel"),
  anomalyContractHorizon: document.querySelector(
    "#anomaly-contract-horizon"
  ),
  anomalyContractSample: document.querySelector(
    "#anomaly-contract-sample"
  ),
  anomalyContractShape: document.querySelector(
    "#anomaly-contract-shape"
  ),
  anomalyContractStride: document.querySelector(
    "#anomaly-contract-stride"
  ),
  anomalyContractThreshold: document.querySelector(
    "#anomaly-contract-threshold"
  ),
  anomalyContractWindow: document.querySelector(
    "#anomaly-contract-window"
  ),
  anomalyEventTable: document.querySelector("#anomaly-event-table"),
  anomalyEventTimeline: document.querySelector(
    "#anomaly-event-timeline"
  ),
  anomalyEvidenceNote: document.querySelector("#anomaly-evidence-note"),
  anomalyFeatureStrip: document.querySelector("#anomaly-feature-strip"),
  anomalyFutureLabels: document.querySelector("#anomaly-future-labels"),
  anomalyFutureSummary: document.querySelector("#anomaly-future-summary"),
  anomalyKpiGrid: document.querySelector("#anomaly-kpi-grid"),
  anomalyKeySignalsChart: document.querySelector(
    "#anomaly-key-signals-chart"
  ),
  anomalyResultContext: document.querySelector("#anomaly-result-context"),
  anomalyTestModelArtifact: document.querySelector(
    "#anomaly-test-model-artifact"
  ),
  anomalyTestModelName: document.querySelector(
    "#anomaly-test-model-name"
  ),
  anomalyTestMachineSelect: document.querySelector(
    "#anomaly-test-machine-select"
  ),
  anomalyTestTimeHint: document.querySelector("#anomaly-test-time-hint"),
  anomalyTestVisualization: document.querySelector(
    "#anomaly-test-visualization"
  ),
  anomalyTestDatasetSelect: document.querySelector(
    "#anomaly-test-dataset-select"
  ),
  anomalyTestTime: document.querySelector("#anomaly-test-time"),
  anomalyWindowHeatmap: document.querySelector(
    "#anomaly-window-heatmap"
  ),
  anomalyWindowShape: document.querySelector("#anomaly-window-shape"),
  constructionModelTab: document.querySelector("#construction-model-tab"),
  constructionModelPanel: document.querySelector(
    "#construction-model-panel"
  ),
  constructionTestDatasetSelect: document.querySelector(
    "#construction-test-dataset-select"
  ),
  constructionTestMethodSelect: document.querySelector(
    "#construction-test-method-select"
  ),
  hlsModelTab: document.querySelector("#hls-model-tab"),
  hlsModelPanel: document.querySelector("#hls-model-panel"),
  hlsGanttChart: document.querySelector("#hls-gantt-chart"),
  hlsGanttSection: document.querySelector("#hls-gantt-section"),
  hlsGanttTooltip: document.querySelector("#hls-gantt-tooltip"),
  hlsTestDatasetSelect: document.querySelector(
    "#hls-test-dataset-select"
  ),
  hlsTestMaxIter: document.querySelector("#hls-test-max-iter"),
  hlsTestMaxRepeat: document.querySelector("#hls-test-max-repeat"),
  hlsTestPopulation: document.querySelector("#hls-test-population"),
  hlsTestRandomStrategy: document.querySelector(
    "#hls-test-random-strategy"
  ),
  hlsTestSearchMode: document.querySelector("#hls-test-search-mode"),
  hlsTestSeed: document.querySelector("#hls-test-seed"),
  hlsTestTabuLength: document.querySelector("#hls-test-tabu-length"),
  hlsTestTime: document.querySelector("#hls-test-time"),
  modelTestOutput: document.querySelector("#model-test-output"),
  modelTestPage: document.querySelector("#model-test-page"),
  modelTestGanttSubtitle: document.querySelector(
    "#model-test-gantt-subtitle"
  ),
  modelTestGanttTitle: document.querySelector("#model-test-gantt-title"),
  modelTestRawDetails: document.querySelector("#model-test-raw-details"),
  modelTestSummary: document.querySelector("#model-test-summary"),
  modelTestStatus: document.querySelector("#model-test-status"),
  modelTestViewButton: document.querySelector("#model-test-view-button"),
  monitorPage: document.querySelector("#monitor-page"),
  monitorViewButton: document.querySelector("#monitor-view-button"),
  manualJobInsertButton: document.querySelector(
    "#manual-job-insert-button"
  ),
  machineLanes: document.querySelector("#machine-lanes"),
  makespan: document.querySelector("#makespan"),
  orderCount: document.querySelector("#order-count"),
  orderList: document.querySelector("#order-list"),
  pauseButton: document.querySelector("#pause-button"),
  playhead: document.querySelector("#playhead"),
  processTabs: document.querySelector("#process-tabs"),
  reoptimizeButton: document.querySelector("#reoptimize-button"),
  reoptimizerSelect: document.querySelector("#reoptimizer-select"),
  runAnomalyModelTestButton: document.querySelector(
    "#run-anomaly-model-test-button"
  ),
  runConstructionModelTestButton: document.querySelector(
    "#run-construction-model-test-button"
  ),
  runHlsModelTestButton: document.querySelector(
    "#run-hls-model-test-button"
  ),
  clearModelTestResultButton: document.querySelector(
    "#clear-model-test-result-button"
  ),
  scheduleTab: document.querySelector("#schedule-tab"),
  scheduleView: document.querySelector("#schedule-view"),
  speedSelect: document.querySelector("#speed-select"),
  startButton: document.querySelector("#start-button"),
  stopButton: document.querySelector("#stop-button"),
  timeAxis: document.querySelector("#time-axis"),
  timelineBody: document.querySelector("#timeline-body"),
  totalEnergy: document.querySelector("#total-energy"),
  topbar: document.querySelector(".topbar"),
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
  constructionMethods: [
    "FIFO_SPT",
    "FIFO_EET",
    "MOPNR_SPT",
    "MOPNR_EET",
    "MWKR_SPT",
    "MWKR_EET",
    "InfluenceAwareConstruct",
  ],
  displayPercent: 100,
  speed: 5,
  status: "idle",
  lanes: new Map(),
  bars: new Map(),
  transportSegments: new Map(),
  materialAnomalyIntervals: new Map(),
  pendingMaterialAnomalyEvents: new Map(),
  pendingMaterialAnomalyOperations: new Map(),
  nextOperationStart: new Map(),
  pendingSignatures: new Map(),
  transportPlanSignature: null,
  lastPendingQueueRenderAt: 0,
  planRevision: null,
  jobGroupOpen: { ...DEFAULT_JOB_GROUP_OPEN },
  jobGroups: new Map(),
  jobStates: [],
  orderBatches: [],
  orderListSignature: null,
  cancelRequestPending: false,
  anomalyCount: 0,
  anomalyHandlingEnabled: false,
  machineStates: [],
  processCatalog: [],
  processCatalogSignature: null,
  processTabButtons: new Map(),
  processPlans: new Map(),
  processMachineStates: new Map(),
  activeProcessId: 1,
  latestSnapshot: null,
  machineCards: new Map(),
  machineDetection: new Map(),
  materialCatalog: {},
  detectionBuffers: new Map(),
  detectionMachines: [],
  detectionPredictions: new Map(),
  detectionProtocol: "legacy",
  detectionMachineCount: null,
  detectionProcessId: null,
  detectionInitialT: 0,
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
  detectionUnavailableProcessId: null,
  activeTab: "schedule",
  activePage: "monitor",
  activeModelTestTab: "anomaly",
  anomalyContextByProcess: new Map(),
  anomalyEventChartInstance: null,
  anomalyFutureChartInstance: null,
  anomalyHeatmapChartInstance: null,
  anomalySignalChartInstance: null,
  hlsGanttChartInstance: null,
  hlsGanttMachineIds: [],
  hlsGanttRows: [],
  reoptimizationAnimationRunning: false,
};
let pollTimer = null;

function formatTime(value) {
  return Number(value || 0).toFixed(value < 10 ? 1 : 0);
}

function operationKey(jobId, operationId) {
  return `${jobId}-${operationId}`;
}

function operationDisplayIndex(operation) {
  if (
    operation.stage_operation_id !== null
    && operation.stage_operation_id !== undefined
  ) {
    const stageOperationId = Number(operation.stage_operation_id);
    if (Number.isFinite(stageOperationId)) {
      return stageOperationId;
    }
  }
  return operation.operation_id;
}

function operationDisplayName(operation) {
  return `J${operation.job_id}-O${operationDisplayIndex(operation)}`;
}

function operationDisplayTitle(operation) {
  const stageIndex = operationDisplayIndex(operation);
  const globalIndex = Number(operation.operation_id);
  const globalSuffix = stageIndex === globalIndex
    ? ""
    : ` / 全局工序 O${globalIndex}`;
  return `作业 ${operation.job_id} / 工艺内工序 O${stageIndex}${globalSuffix}`;
}

function jobHue(jobId) {
  return (185 + Number(jobId) * 137.508) % 360;
}

function resetView() {
  app.after = 0;
  app.lanes.clear();
  app.bars.clear();
  app.transportSegments.clear();
  app.materialAnomalyIntervals.clear();
  app.pendingMaterialAnomalyEvents.clear();
  app.pendingMaterialAnomalyOperations.clear();
  app.nextOperationStart.clear();
  app.pendingSignatures.clear();
  app.transportPlanSignature = null;
  app.lastPendingQueueRenderAt = 0;
  app.planRevision = null;
  app.jobGroupOpen = { ...DEFAULT_JOB_GROUP_OPEN };
  app.jobGroups.clear();
  app.jobStates = [];
  app.orderBatches = [];
  app.orderListSignature = null;
  app.cancelRequestPending = false;
  app.anomalyCount = 0;
  app.machineStates = [];
  app.processCatalog = [];
  app.processCatalogSignature = null;
  app.processTabButtons.clear();
  app.processPlans.clear();
  app.processMachineStates.clear();
  app.activeProcessId = 1;
  app.latestSnapshot = null;
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
  elements.processTabs.replaceChildren();
  elements.materialBoardGrid.replaceChildren();
  elements.anomalyCount.textContent = "0";
  elements.jobCount.textContent = "0";
  elements.timelineBody.scrollTop = 0;
  setDashboardTab(app.activeTab);
}

function setDashboardTab(tab) {
  const validTabs = new Set([
    "schedule",
    "machine-board",
    "material-board",
  ]);
  app.activeTab = validTabs.has(tab) ? tab : "schedule";
  const showingSchedule = app.activeTab === "schedule";
  const showingMachineBoard = app.activeTab === "machine-board";
  const showingMaterialBoard = app.activeTab === "material-board";
  elements.scheduleView.classList.toggle("hidden", !showingSchedule);
  elements.machineBoardView.classList.toggle(
    "hidden",
    !showingMachineBoard,
  );
  elements.materialBoardView.classList.toggle(
    "hidden",
    !showingMaterialBoard,
  );
  elements.scheduleTab.classList.toggle("active", showingSchedule);
  elements.machineBoardTab.classList.toggle(
    "active",
    showingMachineBoard,
  );
  elements.materialBoardTab.classList.toggle(
    "active",
    showingMaterialBoard,
  );
  elements.scheduleTab.setAttribute(
    "aria-selected",
    String(showingSchedule),
  );
  elements.machineBoardTab.setAttribute(
    "aria-selected",
    String(showingMachineBoard),
  );
  elements.materialBoardTab.setAttribute(
    "aria-selected",
    String(showingMaterialBoard),
  );
  if (showingMachineBoard) {
    syncDetectionWithSimulation(app.status);
    window.requestAnimationFrame(() => {
      renderMachineDetectionCharts();
      resizeMachineCharts();
    });
  } else if (showingMaterialBoard) {
    renderMaterialInventoryBoard();
  }
}

function setModelTestStatus(text, status = "idle") {
  elements.modelTestStatus.textContent = text;
  elements.modelTestStatus.className = `status-pill ${status}`;
}

function showModelTestResult(payload) {
  elements.modelTestOutput.textContent = typeof payload === "string"
    ? payload
    : JSON.stringify(payload, null, 2);
}

function clearHlsGantt() {
  if (app.hlsGanttChartInstance) {
    app.hlsGanttChartInstance.dispose();
    app.hlsGanttChartInstance = null;
  }
  elements.hlsGanttChart.replaceChildren();
  hideHlsGanttTooltip();
  elements.hlsGanttSection.classList.add("hidden");
  app.hlsGanttMachineIds = [];
  app.hlsGanttRows = [];
}

function resetModelTestResult() {
  clearHlsGantt();
  clearAnomalyTestVisualization();
  elements.modelTestSummary.replaceChildren();
  elements.modelTestSummary.classList.add("hidden");
  elements.modelTestRawDetails.open = false;
  showModelTestResult("尚未运行模型测试。");
}

function renderModelTestSummary(items) {
  elements.modelTestSummary.replaceChildren();
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "model-test-summary-card";
    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    value.textContent = item.value;
    card.append(label, value);
    elements.modelTestSummary.append(card);
  }
  elements.modelTestSummary.classList.toggle("hidden", items.length === 0);
}

function resizeHlsGanttChart() {
  if (app.hlsGanttChartInstance) {
    app.hlsGanttChartInstance.resize();
  }
}

function hideHlsGanttTooltip() {
  elements.hlsGanttTooltip.classList.add("hidden");
}

function handleHlsGanttMouseMove(event) {
  if (!app.hlsGanttChartInstance) {
    return;
  }
  const point = app.hlsGanttChartInstance.convertFromPixel(
    { gridIndex: 0 },
    [event.offsetX, event.offsetY],
  );
  if (!Array.isArray(point)) {
    hideHlsGanttTooltip();
    return;
  }
  const time = Number(point[0]);
  let machineId = null;
  if (
    Number.isInteger(point[1])
    && point[1] >= 0
    && point[1] < app.hlsGanttMachineIds.length
  ) {
    machineId = app.hlsGanttMachineIds[point[1]];
  } else if (typeof point[1] === "string") {
    const match = point[1].match(/^M(\d+)$/);
    if (match) {
      machineId = Number(match[1]);
    }
  }
  if (!Number.isFinite(time) || machineId === null) {
    hideHlsGanttTooltip();
    return;
  }
  const row = app.hlsGanttRows.find(
    (item) => (
      item.machine_id === machineId
      && time >= item.start_time - 1e-9
      && time <= item.end_time + 1e-9
    ),
  );
  if (!row) {
    hideHlsGanttTooltip();
    return;
  }
  const tooltip = elements.hlsGanttTooltip;
  tooltip.textContent = [
    `机器 M${row.machine_id}`,
    `作业 J${row.job_id} · 工序 O${row.operation_index + 1}`,
    `开始：${formatTime(row.start_time)}`,
    `结束：${formatTime(row.end_time)}`,
    `加工时间：${formatTime(row.end_time - row.start_time)}`,
  ].join("\n");
  tooltip.classList.remove("hidden");
  const container = elements.hlsGanttChart;
  const parent = container.parentElement;
  const originX = container.offsetLeft;
  const originY = container.offsetTop;
  const left = Math.min(
    Math.max(originX + event.offsetX + 14, 8),
    parent.clientWidth - tooltip.offsetWidth - 8,
  );
  const top = Math.min(
    Math.max(originY + event.offsetY + 14, 8),
    parent.clientHeight - tooltip.offsetHeight - 8,
  );
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function renderHlsGantt(schedule, options = {}) {
  const rows = (schedule || []).filter(
    (row) => (
      Number.isFinite(Number(row.machine_id))
      && Number.isFinite(Number(row.start_time))
      && Number.isFinite(Number(row.end_time))
    ),
  );
  if (rows.length === 0 || typeof echarts === "undefined") {
    clearHlsGantt();
    return;
  }
  const machineIds = [...new Set(
    rows.map((row) => Number(row.machine_id)),
  )].sort((left, right) => left - right);
  const machineIndexes = new Map(
    machineIds.map((machineId, index) => [machineId, index]),
  );
  const chartRows = rows.map((row) => ({
    ...row,
    machine_id: Number(row.machine_id),
    start_time: Number(row.start_time),
    end_time: Number(row.end_time),
    job_id: Number(row.job_id),
    operation_index: Number(
      row.operation_index ?? row.operation_id,
    ),
  }));
  clearHlsGantt();
  app.hlsGanttMachineIds = machineIds;
  app.hlsGanttRows = chartRows;
  elements.modelTestGanttTitle.textContent =
    options.title || "调度甘特图";
  elements.modelTestGanttSubtitle.textContent =
    options.subtitle || "按机器展示工序开始与结束时间";
  elements.hlsGanttSection.classList.remove("hidden");
  app.hlsGanttChartInstance = echarts.init(
    elements.hlsGanttChart,
    null,
    { renderer: "canvas" },
  );
  app.hlsGanttChartInstance.setOption({
    animation: false,
    backgroundColor: "transparent",
    grid: {
      left: 74,
      right: 20,
      top: 24,
      bottom: 62,
    },
    tooltip: { show: false },
    dataZoom: [
      { type: "inside", xAxisIndex: 0 },
      {
        type: "slider",
        xAxisIndex: 0,
        height: 17,
        bottom: 12,
        borderColor: "rgba(120,178,194,0.2)",
        fillerColor: "rgba(48,216,210,0.16)",
        textStyle: { color: "#7e9ba6", fontSize: 9 },
      },
    ],
    xAxis: {
      type: "value",
      name: "时间",
      nameTextStyle: { color: "#7e9ba6", fontSize: 10 },
      axisLabel: { color: "#7e9ba6", fontSize: 9 },
      splitLine: { lineStyle: { color: "rgba(120,178,194,0.09)" } },
    },
    yAxis: {
      type: "category",
      data: machineIds.map((machineId) => `M${machineId}`),
      axisLabel: { color: "#b9d4da", fontSize: 10 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(120,178,194,0.2)" } },
      splitLine: { show: true, lineStyle: { color: "rgba(120,178,194,0.08)" } },
    },
    series: [{
      type: "custom",
      silent: true,
      hoverAnimation: false,
      emphasis: { disabled: true },
      select: { disabled: true },
      renderItem: (params, api) => {
        const machineIndex = api.value(0);
        const start = api.coord([api.value(1), machineIndex]);
        const end = api.coord([api.value(2), machineIndex]);
        const laneHeight = api.size([0, 1])[1];
        const height = laneHeight * 0.58;
        const width = Math.max(1, end[0] - start[0]);
        const jobId = Number(api.value(3));
        const operationNumber = Number(api.value(4));
        const children = [{
          type: "rect",
          shape: {
            x: start[0],
            y: start[1] - height / 2,
            width,
            height,
            r: 3,
          },
          style: {
            fill: `hsl(${jobHue(jobId)} 68% 45%)`,
            stroke: `hsl(${jobHue(jobId)} 78% 70%)`,
            lineWidth: 1,
          },
        }];
        if (width > 32) {
          children.push({
            type: "text",
            silent: true,
            style: {
              text: `J${jobId}-O${operationNumber}`,
              x: start[0] + 4,
              y: start[1],
              fill: "#ffffff",
              font: "9px sans-serif",
              verticalAlign: "middle",
            },
          });
        }
        return {
          type: "group",
          silent: false,
          children,
        };
      },
      encode: { x: [1, 2], y: 0 },
      data: chartRows.map((row) => ({
        value: [
          machineIndexes.get(row.machine_id),
          row.start_time,
          row.end_time,
          row.job_id,
          row.operation_index + 1,
        ],
        row,
      })),
    }],
  });
  const zr = app.hlsGanttChartInstance.getZr();
  zr.on("mousemove", handleHlsGanttMouseMove);
  zr.on("globalout", hideHlsGanttTooltip);
  window.requestAnimationFrame(resizeHlsGanttChart);
}

function formatAnomalyProbability(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "--";
  }
  return Math.abs(number) >= 0.9999
    ? number.toFixed(6)
    : number.toFixed(4);
}

function standardizeAnomalyWindow(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return {
      zRows: [],
      means: [],
      deviations: [],
      constants: [],
    };
  }
  const width = rows[0].length;
  const means = [];
  const deviations = [];
  const constants = [];
  for (let column = 0; column < width; column += 1) {
    const values = rows.map((row) => Number(row[column]));
    const finite = values.filter(Number.isFinite);
    const mean = finite.length > 0
      ? finite.reduce((sum, value) => sum + value, 0) / finite.length
      : 0;
    const variance = finite.length > 0
      ? finite.reduce(
        (sum, value) => sum + (value - mean) ** 2,
        0,
      ) / finite.length
      : 0;
    const deviation = Math.sqrt(variance);
    means.push(mean);
    deviations.push(deviation);
    constants.push(deviation < 1e-9);
  }
  const zRows = rows.map((row) => row.map((value, column) => {
    const number = Number(value);
    if (!Number.isFinite(number) || constants[column]) {
      return 0;
    }
    return Math.max(
      -3,
      Math.min(3, (number - means[column]) / deviations[column]),
    );
  }));
  return { zRows, means, deviations, constants };
}

function disposeAnomalyChart(property) {
  if (app[property]) {
    app[property].dispose();
    app[property] = null;
  }
}

function clearAnomalyTestVisualization() {
  disposeAnomalyChart("anomalyHeatmapChartInstance");
  disposeAnomalyChart("anomalySignalChartInstance");
  disposeAnomalyChart("anomalyFutureChartInstance");
  disposeAnomalyChart("anomalyEventChartInstance");
  elements.anomalyKpiGrid.replaceChildren();
  elements.anomalyEventTable.replaceChildren();
  elements.anomalyWindowHeatmap.replaceChildren();
  elements.anomalyKeySignalsChart.replaceChildren();
  elements.anomalyFutureLabels.replaceChildren();
  elements.anomalyEventTimeline.replaceChildren();
  elements.anomalyEvidenceNote.textContent = "";
  elements.anomalyResultContext.textContent = "等待模型输出";
  elements.anomalyTestVisualization.classList.add("hidden");
}

function resizeAnomalyTestCharts() {
  for (const property of [
    "anomalyHeatmapChartInstance",
    "anomalySignalChartInstance",
    "anomalyFutureChartInstance",
    "anomalyEventChartInstance",
  ]) {
    app[property]?.resize();
  }
}

function appendAnomalyKpi(label, value, detail, tone = "") {
  const card = document.createElement("article");
  card.className = "anomaly-kpi";
  if (tone) {
    card.dataset.tone = tone;
  }
  const key = document.createElement("span");
  key.textContent = label;
  const main = document.createElement("strong");
  main.textContent = value;
  const note = document.createElement("small");
  note.textContent = detail;
  card.append(key, main, note);
  elements.anomalyKpiGrid.append(card);
}

function renderAnomalyKpis(result) {
  const summary = result.summary || {};
  const prediction = result.predictions?.[0] || result;
  const probability = Number(
    summary.probability ?? prediction.probability
  );
  const threshold = Number(
    summary.threshold ?? prediction.threshold
  );
  const margin = Number(
    summary.threshold_margin ?? probability - threshold
  );
  const alarm = Boolean(
    summary.is_alarm ?? prediction.is_alarm
  );
  const truthLabel = summary.truth_label;
  const warn = summary.warn;
  const futureCount = Number(summary.future_fault_count || 0);
  const futurePoints = Number(summary.future_point_count || 0);
  const futureRatio = Number(summary.future_fault_ratio || 0);
  const currentEvent = summary.current_event;
  const nextEvent = summary.next_event;
  const nextDelta = summary.next_event_delta;

  elements.anomalyKpiGrid.replaceChildren();
  appendAnomalyKpi(
    "异常概率",
    formatAnomalyProbability(probability),
    `模型 sigmoid 原始输出`,
    alarm ? "alarm" : "good",
  );
  appendAnomalyKpi(
    "模型判定",
    alarm ? "告警" : "正常",
    `阈值 ${formatAnomalyProbability(threshold)}`,
    alarm ? "alarm" : "good",
  );
  appendAnomalyKpi(
    "阈值余量",
    `${margin >= 0 ? "+" : ""}${formatAnomalyProbability(margin)}`,
    margin >= 0 ? "高于决策阈值" : "低于决策阈值",
    margin >= 0 ? "alarm" : "good",
  );
  appendAnomalyKpi(
    "当前真值",
    truthLabel === 1 ? "故障中" : truthLabel === 0 ? "正常" : "无数据",
    warn === 1 ? "处于未来故障预警区" : "当前无预警标签",
    truthLabel === 1 ? "alarm" : warn === 1 ? "warn" : "good",
  );
  appendAnomalyKpi(
    "未来故障点",
    `${futureCount} / ${futurePoints}`,
    futurePoints > 0
      ? `预测范围内占比 ${(futureRatio * 100).toFixed(1)}%`
      : "未来标签不可用",
    futureCount > 0 ? "alarm" : "good",
  );
  appendAnomalyKpi(
    "最近故障",
    currentEvent ? "区间内" : nextEvent ? `T+${nextDelta}` : "范围外",
    currentEvent
      ? `T${currentEvent.start} → T${currentEvent.end}`
      : nextEvent
        ? `下一事件 T${nextEvent.start}`
        : `共 ${summary.event_count || 0} 个历史事件`,
    currentEvent ? "alarm" : nextEvent ? "warn" : "",
  );
}

function renderAnomalyWindowHeatmap(result) {
  const windowPayload = result.window?.window;
  const rows = windowPayload?.data || [];
  const features = windowPayload?.features || [];
  if (
    rows.length === 0
    || features.length === 0
    || typeof window.echarts === "undefined"
  ) {
    elements.anomalyWindowHeatmap.textContent = "输入窗口不可用";
    elements.anomalyWindowShape.textContent = "--";
    return;
  }
  elements.anomalyWindowShape.textContent =
    `${features.length} × ${rows.length}`;
  const { zRows, constants } = standardizeAnomalyWindow(rows);
  const data = [];
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    for (
      let featureIndex = 0;
      featureIndex < features.length;
      featureIndex += 1
    ) {
      data.push({
        value: [
          rowIndex,
          featureIndex,
          zRows[rowIndex][featureIndex],
        ],
        raw: Number(rows[rowIndex][featureIndex]),
        constant: constants[featureIndex],
        itemStyle: constants[featureIndex]
          ? { color: "#485561" }
          : undefined,
      });
    }
  }
  disposeAnomalyChart("anomalyHeatmapChartInstance");
  app.anomalyHeatmapChartInstance = window.echarts.init(
    elements.anomalyWindowHeatmap,
    null,
    { renderer: "canvas" },
  );
  app.anomalyHeatmapChartInstance.setOption({
    animation: false,
    backgroundColor: "transparent",
    grid: {
      left: 94,
      right: 14,
      top: 12,
      bottom: 56,
    },
    tooltip: {
      position: "top",
      borderWidth: 0,
      backgroundColor: "rgba(4, 18, 27, 0.96)",
      textStyle: { color: "#d8f0f3", fontSize: 10 },
      formatter: (params) => {
        const item = params.data;
        return [
          `<b>${features[item.value[1]]}</b>`,
          `窗口点：${item.value[0]}`,
          `原始值：${Number.isFinite(item.raw) ? item.raw : "--"}`,
          `标准分：${item.constant ? "常量通道" : item.value[2].toFixed(3)}`,
        ].join("<br>");
      },
    },
    xAxis: {
      type: "category",
      data: rows.map((_, index) => String(index)),
      axisLabel: {
        color: "#718b94",
        fontSize: 8,
        interval: Math.max(0, Math.ceil(rows.length / 8) - 1),
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(120,178,194,0.15)" } },
    },
    yAxis: {
      type: "category",
      data: features,
      inverse: true,
      axisLabel: {
        color: "#9fb9c0",
        fontSize: 8,
        fontFamily: "Cascadia Mono, monospace",
      },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    visualMap: {
      min: -3,
      max: 3,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 12,
      itemWidth: 110,
      itemHeight: 7,
      text: ["高", "低"],
      textStyle: { color: "#718b94", fontSize: 8 },
      inRange: {
        color: ["#2458a6", "#172a3d", "#a53e4f"],
      },
    },
    series: [{
      type: "heatmap",
      data,
      emphasis: {
        itemStyle: {
          borderColor: "#dffdf7",
          borderWidth: 1,
        },
      },
    }],
  });
}

function renderAnomalySignalChart(result) {
  const windowPayload = result.window?.window;
  const rows = windowPayload?.data || [];
  const features = windowPayload?.features || [];
  if (
    rows.length === 0
    || features.length === 0
    || typeof window.echarts === "undefined"
  ) {
    elements.anomalyKeySignalsChart.textContent = "信号窗口不可用";
    return;
  }
  const requested = [
    "TP2",
    "DV_pressure",
    "Oil_temperature",
    "Motor_current",
  ];
  const selected = requested
    .map((name) => ({
      name,
      index: features.indexOf(name),
    }))
    .filter((item) => item.index >= 0);
  if (selected.length === 0) {
    elements.anomalyKeySignalsChart.textContent = "关键信号不可用";
    return;
  }
  const { zRows } = standardizeAnomalyWindow(rows);
  const colors = ["#30d8d2", "#ffbd59", "#ff667d", "#4a9fff"];
  disposeAnomalyChart("anomalySignalChartInstance");
  app.anomalySignalChartInstance = window.echarts.init(
    elements.anomalyKeySignalsChart,
    null,
    { renderer: "canvas" },
  );
  app.anomalySignalChartInstance.setOption({
    animation: false,
    backgroundColor: "transparent",
    color: colors,
    legend: {
      top: 0,
      right: 4,
      itemWidth: 10,
      itemHeight: 3,
      textStyle: { color: "#819ca5", fontSize: 8 },
    },
    grid: {
      left: 42,
      right: 18,
      top: 36,
      bottom: 32,
    },
    tooltip: {
      trigger: "axis",
      borderWidth: 0,
      backgroundColor: "rgba(4, 18, 27, 0.96)",
      textStyle: { color: "#d8f0f3", fontSize: 10 },
      formatter: (items) => {
        const index = items[0]?.dataIndex ?? 0;
        return [
          `<b>窗口点 ${index}</b>`,
          ...selected.map((item) => (
            `${item.name}：${rows[index][item.index]}`
            + `（z=${zRows[index][item.index].toFixed(2)}）`
          )),
        ].join("<br>");
      },
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: rows.map((_, index) => String(index)),
      axisLabel: {
        color: "#718b94",
        fontSize: 8,
        interval: Math.max(0, Math.ceil(rows.length / 8) - 1),
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(120,178,194,0.15)" } },
    },
    yAxis: {
      type: "value",
      name: "通道标准分",
      nameTextStyle: { color: "#718b94", fontSize: 8 },
      axisLabel: { color: "#718b94", fontSize: 8 },
      splitLine: {
        lineStyle: { color: "rgba(120,178,194,0.08)" },
      },
    },
    series: selected.map((item, seriesIndex) => ({
      name: item.name,
      type: "line",
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 1.4 },
      emphasis: { focus: "series" },
      data: zRows.map((row) => row[item.index]),
      markLine: seriesIndex === 0 ? {
        silent: true,
        symbol: "none",
        lineStyle: {
          color: "rgba(255,255,255,0.16)",
          type: "dashed",
        },
        label: { show: false },
        data: [{ yAxis: 0 }],
      } : undefined,
    })),
  });
}

function renderAnomalyFutureLabels(result) {
  const frames = result.future?.frames || [];
  const summary = result.summary || {};
  if (frames.length === 0 || typeof window.echarts === "undefined") {
    elements.anomalyFutureLabels.textContent = "未来标签不可用";
    elements.anomalyFutureSummary.textContent = "--";
    return;
  }
  elements.anomalyFutureSummary.textContent =
    `${summary.future_fault_count || 0} / `
    + `${summary.future_point_count || frames.length}`;
  const colors = frames.map((frame) => {
    if (Number(frame.label) === 1) {
      return "#ff667d";
    }
    if (Number(frame.warn) === 1) {
      return "#ffbd59";
    }
    return "#315c67";
  });
  disposeAnomalyChart("anomalyFutureChartInstance");
  app.anomalyFutureChartInstance = window.echarts.init(
    elements.anomalyFutureLabels,
    null,
    { renderer: "canvas" },
  );
  app.anomalyFutureChartInstance.setOption({
    animation: false,
    backgroundColor: "transparent",
    grid: {
      left: 18,
      right: 12,
      top: 18,
      bottom: 30,
    },
    tooltip: {
      trigger: "item",
      borderWidth: 0,
      backgroundColor: "rgba(4, 18, 27, 0.96)",
      textStyle: { color: "#d8f0f3", fontSize: 10 },
      formatter: (params) => [
        `<b>时间点 T${params.data.frame.t}</b>`,
        `真值：${params.data.frame.label}`,
        `预警区：${params.data.frame.warn}`,
      ].join("<br>"),
    },
    xAxis: {
      type: "category",
      data: frames.map((frame) => `T${frame.t}`),
      axisLabel: {
        color: "#718b94",
        fontSize: 8,
        interval: frames.length > 10 ? 1 : 0,
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(120,178,194,0.15)" } },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      show: false,
    },
    series: [{
      type: "bar",
      barWidth: "78%",
      data: frames.map((frame, index) => ({
        value: 1,
        frame,
        itemStyle: {
          color: colors[index],
          borderRadius: [3, 3, 0, 0],
        },
      })),
    }],
  });
}

function renderAnomalyEvents(result) {
  const payload = result.events || {};
  const events = [...(payload.events || [])]
    .map((event, index) => ({ ...event, index }))
    .sort((left, right) => Number(left.start) - Number(right.start));
  const effectiveT = Number(
    result.input_parameters?.t_effective
      ?? result.t_effective
      ?? result.t
      ?? 0
  );
  elements.anomalyEventTable.replaceChildren();
  if (events.length === 0) {
    elements.anomalyEventTimeline.textContent = "无故障事件数据";
    return;
  }

  const nextIndex = events.findIndex(
    (event) => Number(event.start) > effectiveT,
  );
  const indexes = new Set();
  if (nextIndex < 0) {
    indexes.add(events.length - 1);
    indexes.add(events.length - 2);
    indexes.add(events.length - 3);
  } else {
    indexes.add(nextIndex);
    indexes.add(nextIndex - 1);
    indexes.add(nextIndex + 1);
  }
  for (const index of [...indexes]
    .filter((item) => item >= 0 && item < events.length)
    .sort((left, right) => left - right)) {
    const event = events[index];
    const active = effectiveT >= Number(event.start)
      && effectiveT <= Number(event.end);
    const row = document.createElement("div");
    row.className = `anomaly-event-row${active ? " active" : ""}`;
    const label = document.createElement("b");
    label.textContent = `E${event.index + 1}`;
    const period = document.createElement("time");
    period.textContent = `T${event.start} → T${event.end}`;
    const status = document.createElement("span");
    status.textContent = active
      ? "覆盖测试点"
      : Number(event.start) > effectiveT
        ? `+${Number(event.start) - effectiveT}`
        : `-${effectiveT - Number(event.end)}`;
    row.append(label, period, status);
    elements.anomalyEventTable.append(row);
  }

  if (typeof window.echarts === "undefined") {
    elements.anomalyEventTimeline.textContent = "事件时间轴不可用";
    return;
  }
  disposeAnomalyChart("anomalyEventChartInstance");
  app.anomalyEventChartInstance = window.echarts.init(
    elements.anomalyEventTimeline,
    null,
    { renderer: "canvas" },
  );
  app.anomalyEventChartInstance.setOption({
    animation: false,
    backgroundColor: "transparent",
    grid: {
      left: 76,
      right: 18,
      top: 20,
      bottom: 30,
    },
    tooltip: {
      trigger: "item",
      borderWidth: 0,
      backgroundColor: "rgba(4, 18, 27, 0.96)",
      textStyle: { color: "#d8f0f3", fontSize: 10 },
      formatter: (params) => {
        const event = params.data?.event
          || events[params.dataIndex];
        if (!event) {
          return "";
        }
        return [
          `<b>故障事件 E${event.index + 1}</b>`,
          `开始：T${event.start}`,
          `结束：T${event.end}`,
          `持续：${Number(event.duration ?? (
            Number(event.end) - Number(event.start)
          ))} 点`,
        ].join("<br>");
      },
    },
    xAxis: {
      type: "value",
      min: 0,
      max: Math.max(
        Number(events.at(-1)?.end || 0),
        effectiveT,
      ),
      name: "时间点",
      nameTextStyle: { color: "#718b94", fontSize: 8 },
      axisLabel: {
        color: "#718b94",
        fontSize: 8,
        formatter: (value) => `T${Math.round(value)}`,
      },
      splitLine: {
        lineStyle: { color: "rgba(120,178,194,0.07)" },
      },
    },
    yAxis: {
      type: "category",
      data: ["真实故障"],
      axisLabel: { color: "#9fb9c0", fontSize: 9 },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [{
      type: "custom",
      data: events.map((event) => ({
        value: [Number(event.start), Number(event.end), 0],
        event,
      })),
      renderItem: (params, api) => {
        const start = api.coord([api.value(0), 0]);
        const end = api.coord([api.value(1), 0]);
        const height = api.size([0, 1])[1] * 0.46;
        const event = params.data?.event
          || events[params.dataIndex];
        const active = effectiveT >= Number(event.start)
          && effectiveT <= Number(event.end);
        return {
          type: "rect",
          shape: {
            x: start[0],
            y: start[1] - height / 2,
            width: Math.max(2, end[0] - start[0]),
            height,
            r: 3,
          },
          style: {
            fill: active
              ? "#ff667d"
              : "rgba(255,102,125,0.68)",
            stroke: active
              ? "#ffd4da"
              : "rgba(255,102,125,0.36)",
            lineWidth: 1,
          },
        };
      },
      encode: { x: [0, 1], y: 2 },
    }, {
      type: "line",
      data: [],
      symbol: "none",
      silent: true,
      markLine: {
        silent: true,
        symbol: "none",
        lineStyle: {
          color: "#ffbd59",
          width: 1.2,
          type: "dashed",
        },
        label: {
          color: "#ffbd59",
          fontSize: 8,
          formatter: `测试点 T${effectiveT}`,
        },
        data: [{ xAxis: effectiveT }],
      },
    }],
  });
}

function showAnomalyModelResult(payload) {
  const result = payload.result || {};
  const predictions = result.predictions || [];
  const hasDetailedEvidence = Boolean(result.window?.window?.data);
  if (!hasDetailedEvidence) {
    renderModelTestSummary([
      { label: "测试时间", value: String(result.t ?? "--") },
      { label: "检测机器数", value: String(result.machine_count ?? "--") },
      {
        label: "告警机器数",
        value: String(
          predictions.filter((item) => item.is_alarm).length
        ),
      },
    ]);
    clearAnomalyTestVisualization();
    clearHlsGantt();
    showModelTestResult(payload);
    elements.modelTestRawDetails.open = false;
    return;
  }

  renderModelTestSummary([]);
  clearHlsGantt();
  elements.anomalyTestVisualization.classList.remove("hidden");
  const input = result.input_parameters || {};
  const prediction = result.predictions?.[0] || result;
  elements.anomalyResultContext.textContent =
    `冲压 · M${input.machine_id ?? prediction.machine_id ?? 0}`
    + ` · 有效时间点 T${input.t_effective ?? prediction.t_effective}`
    + ` · P=${formatAnomalyProbability(prediction.probability)}`;
  elements.anomalyContractThreshold.textContent =
    formatAnomalyProbability(result.model?.threshold);
  elements.anomalyTestModelName.textContent =
    result.model?.name || "MetroPT CNN-LSTM";
  elements.anomalyTestModelArtifact.textContent =
    `${result.model?.artifact || "metropt_model.pth"}`
    + ` · ${result.model?.device || "cpu"}`;

  renderAnomalyKpis(result);
  renderAnomalyWindowHeatmap(result);
  renderAnomalySignalChart(result);
  renderAnomalyFutureLabels(result);
  renderAnomalyEvents(result);
  const errors = Object.entries(result.evidence_errors || {});
  elements.anomalyEvidenceNote.textContent = errors.length > 0
    ? `部分证据未返回：${errors.map(([name, message]) => (
      `${name}（${message}）`
    )).join("；")}`
    : "热力图与趋势图使用模型窗口内的原始值计算通道标准分；"
      + "概率、判定、阈值和真值均直接来自检测服务，测试不会注入设备异常事件。";
  showModelTestResult(payload);
  elements.modelTestRawDetails.open = false;
  window.requestAnimationFrame(resizeAnomalyTestCharts);
}

function showHlsModelResult(payload) {
  const result = payload.result || {};
  const objectives = result.objectives || {};
  renderModelTestSummary([
    { label: "优化目标 · Makespan", value: String(objectives.makespan ?? "--") },
    { label: "求解耗时", value: `${result.runtime_seconds ?? "--"} 秒` },
    { label: "作业数", value: String(result.n_jobs ?? "--") },
    { label: "机器数", value: String(result.n_machines ?? "--") },
    { label: "工序数", value: String(result.n_operations ?? "--") },
    { label: "方案可行", value: result.feasible ? "是" : "否" },
  ]);
  renderHlsGantt(result.schedule || [], {
    title: "HLS 调度甘特图",
    subtitle: "按机器展示工序开始与结束时间",
  });
  showModelTestResult(payload);
  elements.modelTestRawDetails.open = false;
}

function showConstructionModelResult(payload) {
  const result = payload.result || payload;
  const objectives = result.objectives || {};
  const breakdown = result.objective_breakdown || {};
  const schedule = result.schedule || {};
  const processName = (
    result.request?.process_id
    && app.datasetCatalog
      .find((dataset) => dataset.id === result.dataset_id)
      ?.processes
      ?.find(
        (process) => (
          Number(process.id) === Number(result.request.process_id)
        ),
      )?.name
  ) || `工艺${result.process_id || result.request?.process_id || 1}`;
  renderModelTestSummary([
    {
      label: "构造方法",
      value: constructionMethodDisplayName(result.method) || "--",
    },
    { label: "测试工艺", value: processName },
    {
      label: "优化目标 · Makespan",
      value: String(objectives.makespan ?? "--"),
    },
    {
      label: "交付成本",
      value: String(objectives.delivery_cost ?? "--"),
    },
    {
      label: "总能耗",
      value: String(objectives.total_energy ?? "--"),
    },
    {
      label: "加工时间",
      value: String(breakdown.processing_time ?? "--"),
    },
    {
      label: "运输时间",
      value: String(breakdown.transport_time ?? "--"),
    },
    {
      label: "作业 / 机器 / 工序",
      value: `${schedule.job_count ?? "--"} / `
        + `${schedule.machine_count ?? "--"} / `
        + `${schedule.operation_count ?? "--"}`,
    },
  ]);
  renderHlsGantt(schedule.operations || [], {
    title: `${
      constructionMethodDisplayName(result.method) || "构造方法"
    } 调度甘特图`,
    subtitle: `${processName} · 仅展示加工工序，运输开销计入优化目标`,
  });
  showModelTestResult(payload);
  elements.modelTestRawDetails.open = false;
}

function setActivePage(page) {
  const normalized = page === "model-test" ? "model-test" : "monitor";
  app.activePage = normalized;
  const showingModelTest = normalized === "model-test";
  elements.monitorPage.classList.toggle("hidden", showingModelTest);
  elements.modelTestPage.classList.toggle("hidden", !showingModelTest);
  elements.topbar.classList.toggle("model-test-mode", showingModelTest);
  elements.monitorViewButton.classList.toggle("active", !showingModelTest);
  elements.modelTestViewButton.classList.toggle("active", showingModelTest);
  elements.monitorViewButton.setAttribute(
    "aria-selected",
    String(!showingModelTest),
  );
  elements.modelTestViewButton.setAttribute(
    "aria-selected",
    String(showingModelTest),
  );
  if (showingModelTest) {
    if (elements.anomalyDialog.open) {
      elements.anomalyDialog.close();
    }
    if (elements.cancelJobsDialog.open) {
      elements.cancelJobsDialog.close();
    }
    syncModelTestDatasets();
    window.requestAnimationFrame(() => {
      resizeHlsGanttChart();
      resizeAnomalyTestCharts();
    });
    return;
  }
  window.requestAnimationFrame(() => {
    resizeMachineCharts();
    renderMachineDetectionCharts();
  });
}

function setModelTestTab(tab) {
  const normalized = ["hls", "construction"].includes(tab)
    ? tab
    : "anomaly";
  app.activeModelTestTab = normalized;
  const showingHls = normalized === "hls";
  const showingConstruction = normalized === "construction";
  const showingAnomaly = normalized === "anomaly";
  elements.anomalyModelPanel.classList.toggle(
    "hidden",
    !showingAnomaly,
  );
  elements.hlsModelPanel.classList.toggle("hidden", !showingHls);
  elements.constructionModelPanel.classList.toggle(
    "hidden",
    !showingConstruction,
  );
  elements.anomalyModelTab.classList.toggle("active", showingAnomaly);
  elements.hlsModelTab.classList.toggle("active", showingHls);
  elements.constructionModelTab.classList.toggle(
    "active",
    showingConstruction,
  );
  elements.anomalyModelTab.setAttribute(
    "aria-selected",
    String(showingAnomaly),
  );
  elements.hlsModelTab.setAttribute(
    "aria-selected",
    String(showingHls),
  );
  elements.constructionModelTab.setAttribute(
    "aria-selected",
    String(showingConstruction),
  );
  syncModelTestDatasets();
  setModelTestStatus("等待测试", "idle");
  resetModelTestResult();
}

function fillSelectOptions(select, options, selectedValue) {
  select.replaceChildren();
  for (const optionData of options) {
    const option = document.createElement("option");
    option.value = String(optionData.value);
    option.textContent = optionData.label;
    select.append(option);
  }
  if (
    selectedValue !== undefined
    && [...select.options].some(
      (option) => option.value === String(selectedValue),
    )
  ) {
    select.value = String(selectedValue);
  }
}

function constructionMethodDisplayName(method) {
  return method === "InfluenceAwareConstruct" ? "IAC" : method;
}

function syncModelTestDatasets() {
  const anomalyProcesses = app.processCatalog.filter(
    (process) => (
      Number(process.id) === 1
      && process.detection_available !== false
    ),
  );
  fillSelectOptions(
    elements.anomalyTestDatasetSelect,
    anomalyProcesses.map((process) => ({
      value: process.id,
      label: `${process.name || "冲压"} · `
        + `${process.machine_count || process.num_machines || 0} 台设备`,
    })),
    elements.anomalyTestDatasetSelect.value || 1,
  );
  if (elements.anomalyTestDatasetSelect.value) {
    void loadAnomalyTestContext(
      Number(elements.anomalyTestDatasetSelect.value),
    ).catch((error) => {
      elements.anomalyTestModelName.textContent = "检测服务不可用";
      elements.anomalyTestModelArtifact.textContent = error.message;
    });
  }
  if (elements.hlsTestDatasetSelect.options.length === 0) {
    fillSelectOptions(
      elements.hlsTestDatasetSelect,
      app.datasetCatalog.map((dataset) => ({
        value: dataset.id,
        label: dataset.label || dataset.name || dataset.id,
      })),
      elements.datasetSelect.value,
    );
  }
  if (elements.constructionTestDatasetSelect.options.length === 0) {
    fillSelectOptions(
      elements.constructionTestDatasetSelect,
      app.datasetCatalog.map((dataset) => ({
        value: dataset.id,
        label: dataset.label || dataset.name || dataset.id,
      })),
      elements.datasetSelect.value,
    );
  }
  fillSelectOptions(
    elements.constructionTestMethodSelect,
    app.constructionMethods.map((method) => ({
      value: method,
      label: constructionMethodDisplayName(method),
    })),
    elements.constructionTestMethodSelect.value
      || "InfluenceAwareConstruct",
  );
}

async function loadConstructionMethods() {
  try {
    const response = await fetch("/api/construction/methods", {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    if (Array.isArray(result.methods) && result.methods.length > 0) {
      app.constructionMethods = [...result.methods];
    }
  } catch (error) {
    // Keep the static fallback list so model testing remains available.
  }
  syncModelTestDatasets();
}

function anomalyProcessMachineCount(processId) {
  const process = app.processCatalog.find(
    (item) => Number(item.id) === Number(processId),
  );
  return Math.max(
    1,
    Number(process?.machine_count || process?.num_machines || 1),
  );
}

function updateAnomalyMachineTimeRange() {
  const processId = Number(
    elements.anomalyTestDatasetSelect.value || 1
  );
  const context = app.anomalyContextByProcess.get(processId);
  const machineId = Number(elements.anomalyTestMachineSelect.value || 0);
  const machine = (context?.machines || []).find(
    (item) => Number(item.machine_id) === machineId,
  );
  const total = Number(machine?.T || 0);
  const maximum = total > 0 ? total - 1 : null;
  if (maximum !== null) {
    elements.anomalyTestTime.max = String(maximum);
    if (
      !Number.isFinite(Number(elements.anomalyTestTime.value))
      || Number(elements.anomalyTestTime.value) > maximum
    ) {
      elements.anomalyTestTime.value = String(Math.min(85, maximum));
    }
  } else {
    elements.anomalyTestTime.removeAttribute("max");
  }
  elements.anomalyTestTimeHint.textContent = total > 0
    ? `范围：0–${maximum} · 当前设备共 ${total} 个时间点`
    : "范围：0 至数据末尾 · 默认：85";
}

function renderAnomalyModelContract(meta, context) {
  const contract = meta.contract || {};
  const features = contract.features
    || (meta.selected_features || [])
      .map((feature) => feature.name)
      .filter(Boolean);
  const shape = contract.model_input_shape
    || [1, features.length, contract.window_size || "--"];
  const threshold = Number(
    meta.ml?.threshold ?? context?.threshold ?? 0
  );
  const stride = contract.step ?? meta.prediction_interval;
  const sample = contract.time_step
    ? `${contract.time_step} s`
    : contract.sample_rate
      ? `${contract.sample_rate} Hz`
      : "--";
  const legacy = meta.protocol === "legacy";

  elements.anomalyContractWindow.textContent =
    contract.window_size ? `${contract.window_size} 点` : "--";
  elements.anomalyContractHorizon.textContent =
    contract.prediction_horizon
      ? `${contract.prediction_horizon} 点`
      : "--";
  elements.anomalyContractStride.textContent =
    stride !== undefined ? `${stride}` : "--";
  elements.anomalyContractShape.textContent =
    Array.isArray(shape) ? shape.join(" × ") : String(shape);
  elements.anomalyContractSample.textContent = sample;
  elements.anomalyContractThreshold.textContent = threshold
    ? threshold.toFixed(6)
    : "--";
  elements.anomalyTestModelName.textContent = legacy
    ? "MetroPT CNN-LSTM"
    : (meta.ml?.model_name || "异常检测模型");
  elements.anomalyTestModelArtifact.textContent = legacy
    ? "metropt_model.pth · 冲压设备故障预测"
    : `${meta.service || "检测服务"} · ${meta.version || ""}`;
  elements.anomalyFeatureStrip.replaceChildren();
  for (const feature of features) {
    const chip = document.createElement("span");
    chip.className = "anomaly-feature-chip";
    chip.textContent = feature;
    elements.anomalyFeatureStrip.append(chip);
  }
}

async function loadAnomalyTestContext(processId, force = false) {
  processId = Number(processId || 1);
  let context = app.anomalyContextByProcess.get(processId);
  if (!context || force) {
    elements.anomalyTestModelName.textContent = "正在读取模型...";
    const responses = await Promise.all([
      fetch(`/api/detection/meta?process_id=${processId}`, {
        cache: "no-store",
      }),
      fetch(`/api/detection/machines?process_id=${processId}`, {
        cache: "no-store",
      }),
    ]);
    for (const response of responses) {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
    }
    const [meta, machines] = await Promise.all(
      responses.map((response) => response.json()),
    );
    context = {
      meta,
      machines: machines.machines || [],
    };
    app.anomalyContextByProcess.set(processId, context);
  }

  renderAnomalyModelContract(context.meta, context);
  const machineLimit = anomalyProcessMachineCount(processId);
  const machineOptions = (context.machines || [])
    .filter((machine) => Number(machine.machine_id) < machineLimit)
    .map((machine) => ({
      value: machine.machine_id,
      label: `M${machine.machine_id} · ${machine.T || "--"} 个时间点`,
    }));
  fillSelectOptions(
    elements.anomalyTestMachineSelect,
    machineOptions,
    elements.anomalyTestMachineSelect.value || 0,
  );
  updateAnomalyMachineTimeRange();
}

async function runAnomalyModelTest() {
  const processId = Number(elements.anomalyTestDatasetSelect.value || 1);
  const predictionTimeValue = elements.anomalyTestTime.value;
  const predictionTime = predictionTimeValue === ""
    ? 85
    : Number(predictionTimeValue);
  const machineId = Number(
    elements.anomalyTestMachineSelect.value || 0
  );
  const maximumTime = elements.anomalyTestTime.max === ""
    ? null
    : Number(elements.anomalyTestTime.max);
  if (
    !Number.isInteger(predictionTime)
    || predictionTime < 0
    || (
      maximumTime !== null
      && predictionTime > maximumTime
    )
  ) {
    setModelTestStatus("参数无效", "failed");
    showModelTestResult(
      `测试时间点必须是 0–${maximumTime !== null
        ? maximumTime
        : "数据末尾"} 之间的整数。`,
    );
    return;
  }
  const processName = app.processCatalog.find(
    (process) => Number(process.id) === processId,
  )?.name || `工艺${processId}`;
  resetModelTestResult();
  elements.runAnomalyModelTestButton.disabled = true;
  setModelTestStatus("异常检测测试中", "running");
  showModelTestResult(`正在执行异常检测模型 · ${processName} ...`);
  try {
    const response = await fetch("/api/model-test/anomaly", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        process_id: processId,
        t: predictionTime,
        machine_id: machineId,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    setModelTestStatus("测试完成", "finished");
    showAnomalyModelResult(result);
  } catch (error) {
    setModelTestStatus("测试失败", "failed");
    renderModelTestSummary([]);
    clearHlsGantt();
    showModelTestResult(`异常检测模型测试失败：${error.message}`);
  } finally {
    elements.runAnomalyModelTestButton.disabled = false;
  }
}

async function runHlsModelTest() {
  const datasetId = elements.hlsTestDatasetSelect.value;
  const datasetLabel = elements.hlsTestDatasetSelect.selectedOptions[0]
    ?.textContent || datasetId;
  resetModelTestResult();
  elements.runHlsModelTestButton.disabled = true;
  setModelTestStatus("HLS 测试中", "running");
  showModelTestResult(
    `正在执行 HLS 调度模型 · ${datasetLabel} ...`,
  );
  try {
    const response = await fetch("/api/model-test/hls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        seed: Number(elements.hlsTestSeed.value || 0),
        total_time_seconds: Number(elements.hlsTestTime.value || 20),
        search_mode: Number(elements.hlsTestSearchMode.value || 0.6),
        random_strategy: Number(
          elements.hlsTestRandomStrategy.value || 0.5
        ),
        max_repeat_count: Number(
          elements.hlsTestMaxRepeat.value || 1000
        ),
        max_iter_count: Number(elements.hlsTestMaxIter.value || 45),
        population_size: Number(elements.hlsTestPopulation.value || 32),
        tabu_length: Number(elements.hlsTestTabuLength.value || 30),
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    setModelTestStatus("测试完成", "finished");
    showHlsModelResult(result);
  } catch (error) {
    setModelTestStatus("测试失败", "failed");
    renderModelTestSummary([]);
    clearHlsGantt();
    showModelTestResult(`HLS 调度模型测试失败：${error.message}`);
  } finally {
    elements.runHlsModelTestButton.disabled = false;
  }
}

async function runConstructionModelTest() {
  const datasetId = elements.constructionTestDatasetSelect.value;
  const processId = 1;
  const method = elements.constructionTestMethodSelect.value
    || "InfluenceAwareConstruct";
  const datasetLabel = (
    elements.constructionTestDatasetSelect.selectedOptions[0]
      ?.textContent
    || datasetId
  );
  const processLabel = "冲压";
  if (!datasetId) {
    setModelTestStatus("参数无效", "failed");
    showModelTestResult("请选择测试数据集和构造方法。");
    return;
  }
  resetModelTestResult();
  elements.runConstructionModelTestButton.disabled = true;
  setModelTestStatus("构造方法测试中", "running");
  showModelTestResult(
    `正在执行 ${constructionMethodDisplayName(method)} · `
      + `${datasetLabel} · ${processLabel} ...`,
  );
  try {
    const response = await fetch("/api/model-test/construction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        process_id: processId,
        method,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    setModelTestStatus("测试完成", "finished");
    showConstructionModelResult(result);
  } catch (error) {
    setModelTestStatus("测试失败", "failed");
    renderModelTestSummary([]);
    clearHlsGantt();
    showModelTestResult(`构造方法测试失败：${error.message}`);
  } finally {
    elements.runConstructionModelTestButton.disabled = false;
  }
}

function currentProcessDefinition() {
  return app.processCatalog.find(
    (process) => Number(process.id) === Number(app.activeProcessId),
  ) || app.processCatalog[0] || {
    id: 1,
    name: "冲压",
    machine_count: Number(
      app.datasetCatalog.find(
        (dataset) => dataset.id === elements.datasetSelect.value,
      )?.num_machines || 1,
    ),
    machine_offset: 0,
    detection_start_t: 0,
  };
}

function renderProcessTabs() {
  if (app.processCatalog.length === 0) {
    return;
  }
  elements.processTabs.replaceChildren();
  app.processTabButtons.clear();
  for (const process of app.processCatalog) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.processId = String(process.id);
    button.className =
      `process-tab${Number(process.id) === Number(app.activeProcessId) ? " active" : ""}`;
    button.textContent = `${process.name || `工艺${process.id}`}`;
    const count = document.createElement("small");
    count.textContent = `M${process.machine_count || 0}`;
    button.append(count);
    const alertIndicators = document.createElement("span");
    alertIndicators.className = "process-alert-indicators";
    const materialAlert = document.createElement("span");
    materialAlert.className = "process-alert-pill material-alert-pill";
    materialAlert.hidden = true;
    const machineAlert = document.createElement("span");
    machineAlert.className = "process-alert-pill machine-alert-pill";
    machineAlert.hidden = true;
    alertIndicators.append(materialAlert, machineAlert);
    button.append(alertIndicators);
    button.addEventListener("click", () => setActiveProcess(process.id));
    elements.processTabs.append(button);
    app.processTabButtons.set(String(process.id), {
      button,
      materialAlert,
      machineAlert,
    });
  }
  refreshProcessTabAlerts();
}

function refreshProcessTabAlerts() {
  if (app.processTabButtons.size === 0) {
    return;
  }
  const materialMachinesByStage = new Map();
  for (const interval of app.materialAnomalyIntervals.values()) {
    if (interval.completed || app.currentTime < interval.start) {
      continue;
    }
    const stageId = String(interval.stageId);
    if (!materialMachinesByStage.has(stageId)) {
      materialMachinesByStage.set(stageId, new Set());
    }
    materialMachinesByStage.get(stageId).add(interval.machineId);
  }

  for (const process of app.processCatalog) {
    const processId = String(process.id);
    const entry = app.processTabButtons.get(processId);
    if (!entry) {
      continue;
    }
    const materialCount =
      materialMachinesByStage.get(processId)?.size || 0;
    const machineStates =
      app.processMachineStates.get(processId) || [];
    const machineCount = machineStates.filter(
      (machine) => (
        Boolean(machine.anomaly_type)
        || ["failed", "repairing", "degraded"].includes(machine.status)
      ),
    ).length;
    const hasMaterialAlert = materialCount > 0;
    const hasMachineAlert = machineCount > 0;

    entry.button.classList.toggle("material-alert", hasMaterialAlert);
    entry.button.classList.toggle("machine-alert", hasMachineAlert);
    entry.button.classList.toggle(
      "has-process-alert",
      hasMaterialAlert || hasMachineAlert,
    );
    entry.materialAlert.hidden = !hasMaterialAlert;
    entry.materialAlert.textContent = `物料 ${materialCount}`;
    entry.machineAlert.hidden = !hasMachineAlert;
    entry.machineAlert.textContent = `设备 ${machineCount}`;

    const details = [
      hasMaterialAlert ? `活动物料异常 ${materialCount} 台` : "",
      hasMachineAlert ? `活动设备异常 ${machineCount} 台` : "",
    ].filter(Boolean);
    entry.button.title = details.length
      ? `${process.name || `工艺${process.id}`} / ${details.join(" / ")}`
      : `${process.name || `工艺${process.id}`}`;
  }
}

function syncProcessCatalog(processes) {
  if (!Array.isArray(processes) || processes.length === 0) {
    return;
  }
  app.processCatalog = [...processes].sort(
    (left, right) => Number(left.id) - Number(right.id),
  );
  if (!app.processCatalog.some(
    (process) => Number(process.id) === Number(app.activeProcessId),
  )) {
    app.activeProcessId = Number(app.processCatalog[0].id);
  }
  const signature = JSON.stringify(
    app.processCatalog.map((process) => [
      process.id,
      process.name,
      process.machine_count,
      process.machine_offset,
      process.detection_start_t,
      process.detection_available,
    ]),
  );
  if (signature !== app.processCatalogSignature) {
    app.processCatalogSignature = signature;
    renderProcessTabs();
  }
  syncModelTestDatasets();
}

function resetTimelineForProcess() {
  app.lanes.clear();
  app.bars.clear();
  app.transportSegments.clear();
  app.nextOperationStart.clear();
  app.pendingSignatures.clear();
  app.transportPlanSignature = null;
  app.lastPendingQueueRenderAt = 0;
  elements.machineLanes.replaceChildren();
}

function renderActiveProcessSchedule() {
  if (!app.latestSnapshot) {
    return;
  }
  const processId = String(app.activeProcessId);
  const plan = app.processPlans.get(processId)
    || app.latestSnapshot.plan
    || [];
  const machineStates = app.processMachineStates.get(processId)
    || app.latestSnapshot.machine_states
    || [];
  resetTimelineForProcess();
  app.machineStates = machineStates;
  renderPlan(plan);
  updateMachineStates(machineStates);
  renderPendingQueues(plan, app.serverTime, true);
  refreshMaterialAnomalyLanes(app.currentTime);
  renderAxis();
  renderPlayhead();
}

function setActiveProcess(processId) {
  const normalizedId = Number(processId);
  if (normalizedId === Number(app.activeProcessId)) {
    return;
  }
  app.activeProcessId = normalizedId;
  renderProcessTabs();
  updateReoptimizeButtonText();
  renderActiveProcessSchedule();
  if (!elements.machineBoardView.classList.contains("hidden")) {
    clearDetectionStream();
    syncDetectionWithSimulation(app.status);
  } else if (
    !elements.materialBoardView.classList.contains("hidden")
  ) {
    renderMaterialInventoryBoard();
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
  const process = currentProcessDefinition();
  const localMachineId = Math.max(
    1,
    Number(machineId) - Number(process.machine_offset || 0) + 1,
  );

  const label = document.createElement("div");
  label.className = "machine-label";
  label.innerHTML = `
    <strong>M${String(localMachineId).padStart(2, "0")}</strong>
    <span class="machine-status-text"></span>
    <span class="material-alert-badge" hidden>缺料</span>
    <span class="machine-alert-badge" hidden>设备异常</span>
  `;
  label.title =
    `${process.name || "工艺"} / 全局机器 ${machineId}`;

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
    status: label.querySelector(".machine-status-text"),
    materialAlert: label.querySelector(".material-alert-badge"),
    machineAlert: label.querySelector(".machine-alert-badge"),
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
    bar.textContent = operationDisplayName(operation);
    bar.title =
      `${operationDisplayTitle(operation)} / `
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
  const signature = (plan || [])
    .flatMap((operation) => (
      (operation.transport_segments || []).map((segment, index) => [
        operation.job_id,
        operation.operation_id,
        index,
        segment.source_machine,
        segment.target_machine,
        segment.transport_start,
        segment.transport_end,
        segment.transport_time,
        segment.completed,
      ].join(":"))
    ))
    .join("|");
  if (signature === app.transportPlanSignature) {
    return;
  }
  app.transportPlanSignature = signature;
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

function materialAnomalyOperationKey(event) {
  return [
    event.machine_id,
    event.job_id,
    event.operation_id,
    event.stage_id ?? 1,
  ].join(":");
}

function materialAnomalyMachineLabel(machineId) {
  const process = currentProcessDefinition();
  const localMachineId = Math.max(
    1,
    Number(machineId) - Number(process.machine_offset || 0) + 1,
  );
  return `M${String(localMachineId).padStart(2, "0")}`;
}

function handleMaterialAnomalyEvent(event) {
  const operationKey = materialAnomalyOperationKey(event);
  if (event.type === "MaterialReplenishmentEvent") {
    const start = Number(event.timestamp);
    const leadTime = Number(event.lead_time || 0);
    const interval = {
      key: `material-${event.id}`,
      eventId: event.id,
      machineId: Number(event.machine_id),
      jobId: Number(event.job_id),
      operationId: Number(event.operation_id),
      stageId: Number(event.stage_id ?? 1),
      start,
      end: leadTime > 0 ? start + leadTime : null,
      shortageMaterials: event.shortage_materials || {},
      replenishmentMaterials: event.replenishment_materials || {},
      completed: false,
    };
    app.materialAnomalyIntervals.set(interval.key, interval);
    app.pendingMaterialAnomalyEvents.set(String(event.id), interval);
    app.pendingMaterialAnomalyOperations.set(operationKey, interval);
    updateHorizon(interval.end ?? start);
    return;
  }

  if (event.type !== "MaterialRecoveryEvent") {
    return;
  }
  const pendingEventKey = event.replenishment_event_id === undefined
    ? ""
    : String(event.replenishment_event_id);
  const interval =
    app.pendingMaterialAnomalyEvents.get(pendingEventKey)
    || app.pendingMaterialAnomalyOperations.get(operationKey);
  if (!interval) {
    return;
  }
  interval.end = Number(event.timestamp);
  interval.completed = true;
  interval.recoveryEventId = event.id;
  app.pendingMaterialAnomalyEvents.delete(String(interval.eventId));
  app.pendingMaterialAnomalyOperations.delete(operationKey);
}

function materialAnomalyTitle(interval) {
  const shortage = formatMaterialEventMap(interval.shortageMaterials);
  const replenishment = formatMaterialEventMap(
    interval.replenishmentMaterials,
  );
  const endText = interval.completed
    ? `恢复于 T+${formatTime(interval.end)}`
    : interval.end === null
      ? "等待恢复事件"
      : `预计 T+${formatTime(interval.end)} 恢复`;
  return [
    "物料异常",
    `作业 ${interval.jobId}`,
    materialAnomalyMachineLabel(interval.machineId),
    `开始于 T+${formatTime(interval.start)} / ${endText}`,
    shortage ? `缺口 ${shortage}` : "",
    replenishment ? `待补 ${replenishment}` : "",
  ].filter(Boolean).join(" / ");
}

function refreshMaterialAnomalyLanes(currentTime) {
  app.currentTime = currentTime;
  const activeStage = String(app.activeProcessId);
  const activeByMachine = new Map();
  for (const interval of app.materialAnomalyIntervals.values()) {
    if (
      String(interval.stageId) !== activeStage
      || interval.completed
      || app.currentTime < interval.start
    ) {
      continue;
    }
    const current = activeByMachine.get(interval.machineId);
    if (!current || interval.start > current.start) {
      activeByMachine.set(interval.machineId, interval);
    }
  }

  for (const [machineId, lane] of app.lanes.entries()) {
    const interval = activeByMachine.get(machineId);
    lane.lane.classList.toggle(
      "has-active-material-anomaly",
      Boolean(interval),
    );
    lane.materialAlert.hidden = !interval;
    if (interval) {
      lane.materialAlert.title = materialAnomalyTitle(interval);
      lane.lane.dataset.materialAnomalyStart = interval.start;
    } else {
      lane.materialAlert.removeAttribute("title");
      delete lane.lane.dataset.materialAnomalyStart;
    }
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
  for (const operation of plan || []) {
    if (TIMELINE_OPERATION_STATUSES.has(operation.status)) {
      ensureBar(operation);
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
  root.style.setProperty("--board-scale", String(scale));
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
  if (!elements.machineBoardView.classList.contains("hidden")) {
    window.requestAnimationFrame(() => {
      renderMachineDetectionCharts();
      resizeMachineCharts();
    });
  } else if (
    !elements.materialBoardView.classList.contains("hidden")
  ) {
    renderMaterialInventoryBoard();
  }
}

function syncAutoJobSubmission(config = {}) {
  elements.autoJobSubmit.checked = Boolean(config.enabled);
}

function syncAutoMachineAnomaly(config = {}) {
  elements.autoMachineAnomaly.checked = Boolean(config.enabled);
}

function syncAnomalyHandling(config = {}) {
  app.anomalyHandlingEnabled = Boolean(config.enabled);
  elements.autoMachineAnomaly.disabled = !app.anomalyHandlingEnabled;
  elements.insertAnomalyButton.disabled =
    !app.anomalyHandlingEnabled || app.status !== "running";
  elements.autoMachineAnomaly.closest("label").title =
    app.anomalyHandlingEnabled
      ? "设备异常处置已启用"
      : "设备异常处置已关闭：仅执行调度计算";
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
  refreshMaterialAnomalyLanes(currentTime);
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
    const anomalyLabel =
      MACHINE_ANOMALY_BADGE_TEXT[state.anomaly_type]
      || (state.status === "failed"
        ? "设备故障"
        : state.status === "repairing"
          ? "维修中"
          : state.status === "degraded"
            ? "降额"
            : "");
    const hasMachineAnomaly = Boolean(anomalyLabel);
    lane.lane.classList.toggle(
      "has-active-machine-anomaly",
      hasMachineAnomaly,
    );
    lane.machineAlert.hidden = !hasMachineAnomaly;
    if (hasMachineAnomaly) {
      lane.machineAlert.textContent = anomalyLabel;
      const recoveryText = state.recovery_time === null
        || state.recovery_time === undefined
        ? "等待恢复"
        : `预计 T+${formatTime(state.recovery_time)} 恢复`;
      lane.machineAlert.title =
        `设备异常 / ${anomalyLabel} / ${recoveryText}`;
    } else {
      lane.machineAlert.removeAttribute("title");
    }
  }
  if (elements.anomalyDialog.open) {
    syncAnomalyMachineAvailability();
  }
  refreshProcessTabAlerts();
}

function formatMaterialQuantity(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "--";
  }
  return numericValue.toLocaleString("zh-CN", {
    maximumFractionDigits: 2,
  });
}

function materialDisplayInfo(materialId) {
  const catalog = app.materialCatalog[materialId] || {};
  const unitText = {
    piece: "件",
    set: "套",
  }[catalog.unit] || catalog.unit || "";
  return {
    name: catalog.material_name || "未命名物料",
    unit: unitText,
  };
}

function createMaterialInventoryCard(machine) {
  const card = document.createElement("article");
  card.className = "material-card";
  card.dataset.machineId = machine.id;

  const heading = document.createElement("div");
  heading.className = "material-card-heading";
  const titleGroup = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent =
    `M${String(machine.local_id || machine.id + 1).padStart(2, "0")}`;
  const subtitle = document.createElement("span");
  subtitle.textContent = `全局机器 ${machine.id}`;
  titleGroup.append(title, subtitle);
  const count = document.createElement("span");
  count.className = "material-kind-count";
  const materials = Object.entries(machine.materials || {});
  count.textContent = `${materials.length} 种`;
  heading.append(titleGroup, count);

  const list = document.createElement("div");
  list.className = "material-stock-list";
  if (materials.length === 0) {
    const empty = document.createElement("div");
    empty.className = "material-stock-empty";
    empty.textContent = "暂无物料库存数据";
    list.append(empty);
  } else {
    materials.sort(([left], [right]) => left.localeCompare(right));
    for (const [materialId, quantity] of materials) {
      const info = materialDisplayInfo(materialId);
      const row = document.createElement("div");
      row.className = "material-stock-row";
      const label = document.createElement("div");
      label.className = "material-stock-label";
      const name = document.createElement("strong");
      name.textContent = info.name;
      label.append(name);
      const amount = document.createElement("div");
      amount.className = "material-stock-amount";
      amount.textContent = formatMaterialQuantity(quantity);
      const unit = document.createElement("small");
      unit.textContent = info.unit;
      amount.append(unit);
      row.append(label, amount);
      list.append(row);
    }
  }
  card.append(heading, list);
  return card;
}

function renderMaterialInventoryBoard() {
  const processId = String(app.activeProcessId);
  const machineStates = app.processMachineStates.get(processId)
    || app.latestSnapshot?.machine_states
    || [];
  if (machineStates.length === 0) {
    elements.materialBoardSummary.textContent = "等待运行开始";
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "开始运行后显示当前工艺机器物料库存";
    elements.materialBoardGrid.replaceChildren(empty);
    return;
  }

  const orderedMachines = [...machineStates].sort(
    (left, right) => (
      Number(left.local_id || left.id)
      - Number(right.local_id || right.id)
    ),
  );
  const materialTypes = new Set();
  for (const machine of orderedMachines) {
    for (const materialId of Object.keys(machine.materials || {})) {
      materialTypes.add(materialId);
    }
  }
  elements.materialBoardSummary.textContent =
    `${currentProcessDefinition().name || "当前工艺"} · `
    + `${orderedMachines.length} 台设备 · ${materialTypes.size} 种物料`;
  const fragment = document.createDocumentFragment();
  for (const machine of orderedMachines) {
    fragment.append(createMaterialInventoryCard(machine));
  }
  elements.materialBoardGrid.replaceChildren(fragment);
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
  title.textContent =
    `${currentProcessDefinition().name || "当前工艺"} · `
    + `检测设备 M${detection.machine_id}`;
  const severityBadge = document.createElement("span");
  severityBadge.className = "machine-severity-badge hidden";
  heading.append(title, severityBadge);

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
    chartNote,
    severityBadge,
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
    `${currentProcessDefinition().name || "当前工艺"} · `
    + `检测设备 ${detections.length} 台 · `
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
      prediction: app.detectionPredictions.get(machineId) || null,
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
      + `&machine_count=${app.detectionMachineCount}`
      + `&process_id=${app.detectionProcessId || 1}`,
      { cache: "no-store" },
    );
    const payload = await response.json();
    if (!response.ok || payload.success === false) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    if (Number(payload.t) !== Number(timestamp)) {
      throw new Error("预测响应时间点与 overview 请求不一致");
    }
    for (const prediction of payload.predictions || []) {
      app.detectionPredictions.set(
        Number(prediction.machine_id),
        prediction,
      );
    }
    app.detectionPredictionError = null;
    renderDetectionBuffers();
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
        + `&machine_count=${app.detectionMachineCount}`
        + `&process_id=${app.detectionProcessId || 1}`,
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

async function initializeMachineDetection(
  machineCount,
  processId = app.activeProcessId,
  initialT = 0,
) {
  if (app.detectionInitializing) {
    return;
  }
  app.detectionInitializing = true;
  pauseDetectionPolling();
  try {
    const count = Math.max(1, Number(machineCount || 1));
    const metaResponse = await fetch(
      `/api/detection/meta?process_id=${Number(processId)}`,
      { cache: "no-store" },
    );
    const meta = await metaResponse.json();
    if (!metaResponse.ok) {
      throw new Error(meta.error || `HTTP ${metaResponse.status}`);
    }
    app.detectionFields = meta.selected_features || [];
    app.detectionProtocol = String(meta.protocol || "legacy");
    app.detectionHistoryPoints = Number(meta.history_points || 60);
    app.detectionPollInterval = Number(meta.poll_interval_ms || 1000);
    app.detectionPredictionInterval = Number(
      meta.prediction_interval || 5,
    );
    app.detectionMachineCount = count;
    app.detectionProcessId = Number(processId);
    app.detectionInitialT = Number(initialT || 0);
    app.detectionStreamGeneration = app.generation;
    app.detectionMachines = [];
    app.detectionT = app.detectionInitialT;
    app.detectionLastPredictionT = null;
    app.detectionPredictionError = null;
    app.detectionBuffers.clear();
    app.detectionPredictions.clear();
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
  app.detectionProcessId = null;
  app.detectionInitialT = 0;
  app.detectionProcessId = null;
  app.detectionInitialT = 0;
  app.detectionMachines = [];
  app.detectionLastPredictionT = null;
  app.detectionPredictionError = null;
  app.detectionUnavailableProcessId = null;
  app.detectionBuffers.clear();
  app.detectionPredictions.clear();
  for (const entry of app.machineCards.values()) {
    entry.chart?.dispose();
  }
  app.machineCards.clear();
  app.machineDetection.clear();
  renderDetectionBuffers();
}

function renderDetectionUnavailable(processId) {
  clearDetectionStream();
  app.detectionUnavailableProcessId = Number(processId);
  elements.machineBoardSummary.textContent =
    "当前工艺暂未接入设备检测数据";
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = "该工艺检测数据源尚未配置";
  elements.machineCardGrid.replaceChildren(empty);
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
  if (app.generation === null || app.processCatalog.length === 0) {
    return;
  }
  const process = currentProcessDefinition();
  const machineCount = Number(process.machine_count || 1);
  const processId = Number(process.id);
  if (process.detection_available === false) {
    if (app.detectionUnavailableProcessId !== processId) {
      renderDetectionUnavailable(processId);
    }
    return;
  }
  app.detectionUnavailableProcessId = null;
  if (
    app.detectionStreamGeneration !== app.generation
    || app.detectionMachineCount !== machineCount
    || app.detectionProcessId !== processId
  ) {
    void initializeMachineDetection(
      machineCount,
      processId,
      process.detection_start_t,
    );
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
  const minimum = Number(field.min ?? field.agg_min);
  const maximum = Number(field.max ?? field.agg_max);
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
  const scale = app.displayPercent / 100;
  for (const [machineId, entry] of app.machineCards.entries()) {
    const detection = app.machineDetection.get(machineId);
    if (!detection) {
      continue;
    }
    entry.detection = detection;
    const prediction = detection.prediction;
    const hasPrediction = prediction && !prediction.error;
    entry.severityBadge.classList.toggle("hidden", !hasPrediction);
    if (hasPrediction) {
      const severityLevel = prediction.severity_level || (
        prediction.is_alarm ? "异常" : "L0"
      );
      const severityName = prediction.severity_name || (
        prediction.is_alarm ? "异常" : "正常"
      );
      entry.severityBadge.textContent =
        `${severityLevel} · ${severityName}`;
      entry.severityBadge.dataset.severity = severityLevel;
      entry.severityBadge.title =
        `异常类型：${prediction.anomaly_type || "normal"}\n`
        + `异常得分：${Number(
          prediction.anomaly_score ?? prediction.probability ?? 0
        ).toFixed(4)}`;
    }
    entry.chartNote.textContent = app.detectionProtocol === "mfddt"
      ? "折线为电机 8 通道趋势 · 等级来自实时检测模型"
      : "折线为归一化趋势 · 橙色背景为预警区 · 红色背景为故障区";
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
          width: (index === 0 ? 1.8 : 1.4) * scale,
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
        top: 1 * scale,
        left: 4 * scale,
        itemWidth: 10 * scale,
        itemHeight: 5 * scale,
        textStyle: {
          color: "#8eaab5",
          fontSize: Math.max(7, 9 * scale),
        },
      },
      grid: {
        top: 32 * scale,
        right: 8 * scale,
        bottom: 18 * scale,
        left: 8 * scale,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(7, 18, 28, 0.96)",
        borderColor: "rgba(120, 178, 194, 0.28)",
        textStyle: {
          color: "#e9f4f7",
          fontSize: Math.max(7, 10 * scale),
        },
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
          if (app.detectionProtocol === "mfddt") {
            const currentPrediction = detection.prediction;
            if (currentPrediction) {
              lines.push(
                `模型等级: ${currentPrediction.severity_level || "-"} `
                + `${currentPrediction.severity_name || ""}`,
                `异常类型: ${currentPrediction.anomaly_type || "-"}`,
              );
            }
          } else {
            lines.push(
              `故障标签: ${detection.label[index]}`,
              `预警区: ${detection.warn[index]}`,
            );
          }
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
          fontSize: Math.max(7, 8 * scale),
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

function jobStatusLabel(job) {
  if (job.status === "processing") {
    return PROCESS_ACTIVE_STATUS_TEXT[Number(job.current_stage)]
      || JOB_STATUS_TEXT.processing;
  }
  return JOB_STATUS_TEXT[job.status] || job.status;
}

function jobGroupKey(job) {
  if (job.status !== "processing") {
    return job.status;
  }
  const stage = Number(job.current_stage);
  return PROCESS_ACTIVE_STATUS_TEXT[stage]
    ? `stage-${stage}`
    : "stage-1";
}

function createJobRow(job) {
  const row = document.createElement("div");
  row.className = `job-row job-${job.status}`;

  const identity = document.createElement("span");
  identity.className = "job-id";
  identity.textContent = `J${String(job.job_id).padStart(3, "0")}`;

  const badge = document.createElement("span");
  badge.className = `job-status-badge ${job.status}`;
  badge.textContent = jobStatusLabel(job);

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
      `O${operationDisplayIndex(current)} · M${current.machine_id} · ${progress}`;
  } else {
    detail.textContent = `等待加工 · ${progress}`;
  }
  row.append(identity, badge, detail);
  return row;
}

function ensureJobGroup(group) {
  if (app.jobGroups.has(group.key)) {
    return app.jobGroups.get(group.key);
  }

  const details = document.createElement("details");
  details.className = `job-group job-group-${group.className}`;
  details.dataset.jobStage = group.stage || group.key;
  details.open =
    app.jobGroupOpen[group.key]
    ?? DEFAULT_JOB_GROUP_OPEN[group.key];

  const summary = document.createElement("summary");
  summary.className = "job-group-summary";
  const label = document.createElement("span");
  label.className = "job-group-label";
  label.textContent = group.label;
  const count = document.createElement("span");
  count.className = "job-group-count";
  count.textContent = "0";
  summary.append(label, count);
  summary.addEventListener("click", () => {
    app.jobGroupOpen[group.key] = !details.open;
  });

  const body = document.createElement("div");
  body.className = "job-group-body";
  details.append(summary, body);
  details.addEventListener("toggle", () => {
    if (details.isConnected) {
      app.jobGroupOpen[group.key] = details.open;
    }
  });
  elements.jobList.append(details);

  const entry = {
    details,
    count,
    body,
    signature: null,
  };
  app.jobGroups.set(group.key, entry);
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
      (job) => jobGroupKey(job) === group.key,
    );
    const entry = ensureJobGroup(group);
    entry.count.textContent = String(groupJobs.length);
    const signature = JSON.stringify(
      groupJobs.map((job) => [
        job.job_id,
        job.status,
        job.current_stage,
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
    return `O${operationDisplayIndex(current)} · M${current.machine_id} · ${progress}`;
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
  chip.textContent = operationDisplayName(operation);
  updatePendingChip(chip, operation);
  return chip;
}

function updatePendingChip(chip, operation) {
  chip.title =
    `待加工：${operationDisplayTitle(operation)} / `
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

function renderPendingQueues(plan, currentTime, force = false) {
  const renderNow = performance.now();
  if (
    !force
    && app.status === "running"
    && renderNow - app.lastPendingQueueRenderAt < 450
  ) {
    return;
  }
  app.lastPendingQueueRenderAt = renderNow;
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
    const chipWidth = 78 * (app.displayPercent / 100) + 6;
    const visibleCount = Math.max(
      1,
      Math.min(8, Math.floor((railWidth - 24) / chipWidth)),
    );
    const visibleOperations = pending.slice(0, visibleCount);
    const visibleKeys = visibleOperations.map((operation) =>
      operationKey(operation.job_id, operation.operation_id)
    );
    const signature = [
      ...visibleKeys,
      `count:${pending.length}`,
      `display:${app.displayPercent}`,
      `width:${railWidth}`,
    ].join("|");
    if (app.pendingSignatures.get(machineId) === signature) {
      for (const operation of visibleOperations) {
        const chip = lane.pendingQueue.querySelector(
          `[data-pending-key="${operationKey(
            operation.job_id,
            operation.operation_id,
          )}"]`,
        );
        if (chip) {
          updatePendingChip(chip, operation);
        }
      }
      continue;
    }
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
  if (
    event.type === "MaterialReplenishmentEvent"
    || event.type === "MaterialRecoveryEvent"
  ) {
    const shortageText = formatMaterialEventMap(
      event.shortage_materials,
    );
    const orderText = formatMaterialEventMap(
      event.replenishment_materials,
    );
    const targetText = formatMaterialEventMap(event.target_materials);
    const addedText = formatMaterialEventMap(event.added_materials);
    const availableText = formatMaterialEventMap(
      event.available_materials,
    );
    const details = [
      shortageText ? `缺口 ${shortageText}` : "",
      targetText ? `阈值 ${targetText}` : "",
      orderText ? `待补 ${orderText}` : "",
      addedText ? `已补 ${addedText}` : "",
      availableText ? `当前 ${availableText}` : "",
    ].filter(Boolean).join(" / ");
    return `作业 ${event.job_id} / S${event.stage_id ?? 1}-O${operationDisplayIndex(event)} / M${event.machine_id}${details ? ` / ${details}` : ""}`;
  }
  if (event.job_id !== undefined && event.operation_id !== undefined) {
    return `作业 ${event.job_id} / S${event.stage_id ?? 1}-O${operationDisplayIndex(event)} / M${event.machine_id ?? "-"}`;
  }
  if (event.machine_id !== undefined && event.anomaly_type) {
    return `机器 M${event.machine_id} / ${event.anomaly_type}`;
  }
  if (event.machine_id !== undefined) {
    return `机器 M${event.machine_id}`;
  }
  return "";
}

function formatMaterialEventMap(materials) {
  if (!materials || typeof materials !== "object") {
    return "";
  }
  return Object.entries(materials)
    .map(([materialId, quantity]) => {
      const info = materialDisplayInfo(materialId);
      return `${info.name} ${formatMaterialQuantity(quantity)}${info.unit}`;
    })
    .join("、");
}

function addAnomalyEvent(event) {
  const empty = elements.anomalyList.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  const row = document.createElement("div");
  row.className = "event-row";
  if (
    event.type === "MaterialReplenishmentEvent"
    || event.type === "MaterialRecoveryEvent"
  ) {
    row.classList.add("material-event");
  }
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
  if (
    event.stage_id !== undefined
    && Number(event.stage_id) !== Number(app.activeProcessId)
  ) {
    return;
  }

  const key = operationKey(event.job_id, event.operation_id);
  let bar = app.bars.get(key);
  if (!bar) {
    bar = ensureBar({
      job_id: event.job_id,
      operation_id: event.operation_id,
      stage_id: event.stage_id,
      stage_operation_id: event.stage_operation_id,
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
    || status === "reoptimizing"
    || status === "animating";
  elements.datasetSelect.disabled =
    status === "running"
    || status === "paused"
    || status === "preparing"
    || status === "reoptimizing"
    || status === "animating";
  elements.reoptimizerSelect.disabled = status !== "running";
  elements.reoptimizeButton.disabled = status !== "running";
  elements.insertAnomalyButton.disabled =
    !app.anomalyHandlingEnabled || status !== "running";
  elements.manualJobInsertButton.disabled = status !== "running";
  elements.cancelJobsButton.disabled = status !== "running";
  elements.pauseButton.disabled =
    status !== "running" && status !== "paused";
  elements.stopButton.disabled =
    status !== "running"
    && status !== "paused"
    && status !== "reoptimizing"
    && status !== "animating";
  elements.pauseButton.textContent =
    status === "paused" ? "继续" : "暂停";
  updateReoptimizeButtonText();
  elements.startButton.textContent =
    ["finished", "stopped"].includes(status) ? "再次运行" : "开始运行";
  if (elements.cancelJobsDialog.open) {
    updateCancelSelection();
  }
  syncDetectionWithSimulation(status);
}

const REOPTIMIZERS = {
  greedy: {
    endpoint: "/api/greedy-reoptimize",
    label: "Greedy",
    buttonLabel: "Greedy 重调度",
    busyLabel: "Greedy 重调度中...",
    payload: {},
  },
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
  influence_aware: {
    endpoint: "/api/influence-aware-reoptimize",
    label: "IAC",
    buttonLabel: "IAC 重调度",
    busyLabel: "IAC 重调度中...",
    payload: { method: "InfluenceAwareConstruct" },
  },
};

function selectedReoptimizer() {
  return REOPTIMIZERS[elements.reoptimizerSelect.value]
    || REOPTIMIZERS.greedy;
}

function updateReoptimizeButtonText() {
  if (
    app.status === "reoptimizing"
    || app.status === "animating"
  ) {
    return;
  }
  const processName = currentProcessDefinition().name || "";
  elements.reoptimizeButton.textContent =
    `${selectedReoptimizer().buttonLabel}${processName ? ` · ${processName}` : ""}`;
}

function waitForAnimationFrame() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(resolve);
  });
}

function pendingQueueSlotPoint(queue, index) {
  const queueRect = queue.getBoundingClientRect();
  const queueStyle = window.getComputedStyle(queue);
  const chipWidth = (
    Number.parseFloat(
      queueStyle.getPropertyValue("--pending-chip-width"),
    ) || 78
  );
  const gap = (
    Number.parseFloat(queueStyle.columnGap || queueStyle.gap) || 6
  );
  const paddingLeft = (
    Number.parseFloat(queueStyle.paddingLeft) || 0
  );
  const slotIndex = Math.max(0, Number(index) || 0);
  const x = Math.min(
    Math.max(
      queueRect.left + paddingLeft + chipWidth / 2
        + slotIndex * (chipWidth + gap),
      queueRect.left + 8,
    ),
    queueRect.right - 8,
  );
  return {
    x,
    y: queueRect.top + queueRect.height / 2,
  };
}

async function animateReoptimizationMoves(payload) {
  const moves = Array.isArray(payload.animation_moves)
    ? payload.animation_moves
    : [];
  if (!payload.animation_required || moves.length === 0) {
    setStatus("running");
    return { success: true, resumed: true, status: "running" };
  }

  app.reoptimizationAnimationRunning = true;
  setStatus("animating");
  await waitForAnimationFrame();
  await waitForAnimationFrame();

  const overlay = document.createElement("div");
  overlay.className = "reoptimization-move-overlay";
  const hud = document.createElement("div");
  hud.className = "reoptimization-move-hud";
  hud.setAttribute("role", "status");
  hud.setAttribute("aria-live", "polite");
  const hudTitle = document.createElement("strong");
  hudTitle.textContent = "IAC 重调度 · 工序队列移动";
  const hudOperation = document.createElement("span");
  hudOperation.textContent = "正在准备队列移动动画...";
  const hudHint = document.createElement("small");
  hudHint.textContent = "运行保持暂停，全部移动完成后自动继续";
  hud.append(hudTitle, hudOperation, hudHint);
  overlay.append(hud);
  document.body.append(overlay);

  const highlightedQueues = new Set();
  const animations = [];
  try {
    for (const [index, move] of moves.entries()) {
      const fromMachineId = Number(
        move.from_queue_machine_id ?? move.from_machine_id
      );
      const toMachineId = Number(
        move.to_queue_machine_id ?? move.to_machine_id
      );
      if (
        !Number.isFinite(fromMachineId)
        || !Number.isFinite(toMachineId)
      ) {
        continue;
      }
      const fromLane = ensureLane(fromMachineId);
      const toLane = ensureLane(toMachineId);
      highlightedQueues.add(fromLane.pendingQueue);
      highlightedQueues.add(toLane.pendingQueue);
      fromLane.pendingQueue.classList.add(
        "reoptimization-queue-source"
      );
      toLane.pendingQueue.classList.add(
        "reoptimization-queue-target"
      );
      const fromLabel = materialAnomalyMachineLabel(fromMachineId);
      const toLabel = materialAnomalyMachineLabel(toMachineId);
      const operationLabel =
        `J${move.job_id}-O${move.operation_id}`;
      const fromQueueIndex = Number(move.from_queue_index || 0);
      const toQueueIndex = Number(move.to_queue_index || 0);
      animations.push(new Promise((resolve) => {
        window.setTimeout(() => {
          hudOperation.textContent =
            `${index + 1}/${moves.length} · ${operationLabel} · `
            + `${fromLabel} 队列 ${fromQueueIndex + 1} → `
            + `${toLabel} 队列 ${toQueueIndex + 1}`;
          const ghost = document.createElement("div");
          ghost.className = "reoptimization-move-ghost";
          ghost.style.setProperty("--move-hue", jobHue(move.job_id));
          ghost.textContent =
            `${operationLabel} ${fromLabel}#${fromQueueIndex + 1} → `
            + `${toLabel}#${toQueueIndex + 1}`;
          const fromPoint = pendingQueueSlotPoint(
            fromLane.pendingQueue,
            fromQueueIndex,
          );
          const toPoint = pendingQueueSlotPoint(
            toLane.pendingQueue,
            toQueueIndex,
          );
          const ghostWidth = 154;
          const startLeft = (
            fromPoint.x - ghostWidth / 2
          );
          const startTop = fromPoint.y - 14;
          const endLeft = toPoint.x - ghostWidth / 2;
          const endTop = toPoint.y - 14;
          ghost.style.left = `${startLeft}px`;
          ghost.style.top = `${startTop}px`;
          overlay.append(ghost);
          const distance = Math.hypot(
            endLeft - startLeft,
            endTop - startTop,
          );
          const duration = 620 + Math.min(360, distance * 0.45);
          const animation = ghost.animate(
            [
              {
                left: `${startLeft}px`,
                top: `${startTop}px`,
                opacity: 0,
                transform: "scale(0.82)",
                offset: 0,
              },
              {
                left: `${startLeft}px`,
                top: `${startTop}px`,
                opacity: 1,
                transform: "scale(1)",
                offset: 0.14,
              },
              {
                left: `${(startLeft + endLeft) / 2}px`,
                top: `${Math.min(startTop, endTop) - 32}px`,
                opacity: 1,
                transform: "scale(1.08)",
                offset: 0.56,
              },
              {
                left: `${endLeft}px`,
                top: `${endTop}px`,
                opacity: 0.18,
                transform: "scale(0.94)",
                offset: 1,
              },
            ],
            {
              duration,
              easing: "cubic-bezier(0.22, 0.75, 0.2, 1)",
              fill: "forwards",
            },
          );
          animation.finished
            .catch(() => {})
            .finally(() => {
              ghost.remove();
              resolve();
            });
        }, index * 85);
      }));
    }
    await Promise.all(animations);
    hudOperation.textContent = "队列调整完成，正在恢复正常运行...";
    await new Promise((resolve) => {
      window.setTimeout(resolve, 260);
    });
  } catch (error) {
    console.warn("Reoptimization move animation was skipped.", error);
  } finally {
    for (const queue of highlightedQueues) {
      queue.classList.remove(
        "reoptimization-queue-source",
        "reoptimization-queue-target",
      );
    }
    overlay.remove();
    app.reoptimizationAnimationRunning = false;
  }

  const response = await fetch(
    "/api/reoptimization-animation-complete",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        animation_id: payload.animation_id,
      }),
    },
  );
  const result = await response.json();
  if (!response.ok || !result.success) {
    throw new Error(
      result.error || `恢复正常运行失败：HTTP ${response.status}`,
    );
  }
  setStatus(result.status || "running");
  return result;
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
      body: JSON.stringify({
        ...optimizer.payload,
        process_id: Number(app.activeProcessId),
        wait_for_animation: true,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    await animateReoptimizationMoves(result);
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

function snapshotRequiresTimelineRebuild(snapshot) {
  if (app.planRevision === null) {
    return true;
  }
  return (snapshot.events || []).some((event) =>
    TIMELINE_REBUILD_EVENT_TYPES.has(event.type)
  );
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
  if (snapshot.processes?.length) {
    syncProcessCatalog(snapshot.processes);
  }
  app.latestSnapshot = snapshot;
  app.processPlans = new Map(
    Object.entries(snapshot.process_plans || {}),
  );
  app.processMachineStates = new Map(
    Object.entries(snapshot.process_machine_states || {}),
  );
  if (snapshot.material_catalog) {
    app.materialCatalog = snapshot.material_catalog;
  }
  const serverTime = Number(snapshot.current_time || 0);
  if (
    snapshot.status === "running"
    || snapshot.status === "reoptimizing"
    || snapshot.status === "animating"
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
  const timelineRebuildRequired =
    snapshotRequiresTimelineRebuild(snapshot);
  const planRevisionChanged =
    app.planRevision !== snapshot.plan_revision;
  if (timelineRebuildRequired) {
    app.planRevision = snapshot.plan_revision;
    renderActiveProcessSchedule();
  } else {
    app.planRevision = snapshot.plan_revision;
    const processId = String(app.activeProcessId);
    const activePlan = app.processPlans.get(processId)
      || snapshot.plan
      || [];
    const activeMachineStates = app.processMachineStates.get(processId)
      || snapshot.machine_states
      || [];
    syncTransportPlan(activePlan);
    updateMachineStates(activeMachineStates);
    renderPendingQueues(
      activePlan,
      snapshot.current_time,
      planRevisionChanged
      || ["finished", "failed", "stopped"].includes(snapshot.status),
    );
  }
  renderAxis();
  renderOrderBatches(snapshot.order_batches);
  renderJobStates(snapshot.job_states);
  if (app.activeTab === "material-board") {
    renderMaterialInventoryBoard();
  }

  for (const event of snapshot.events) {
    if (MATERIAL_ANOMALY_EVENT_TYPES.has(event.type)) {
      handleMaterialAnomalyEvent(event);
    }
    handleOperationEvent(event);
    if (ANOMALY_LIST_EVENT_TYPES.has(event.type)) {
      addAnomalyEvent(event);
    }
  }
  refreshMaterialAnomalyLanes(app.currentTime);
  refreshProcessTabAlerts();
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
  renderPlayhead();
  syncAutoJobSubmission(snapshot.auto_job_submission);
  syncAutoMachineAnomaly(snapshot.auto_machine_anomaly);
  syncAnomalyHandling(snapshot.anomaly_handling);

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
    elements.errorBanner.textContent = `无法连接服务：${error.message}`;
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
    elements.errorBanner.textContent = `启动失败：${error.message}`;
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
    const selectedDataset = app.datasetCatalog.find(
      (dataset) => dataset.id === (result.default_dataset || elements.datasetSelect.value),
    );
    if (selectedDataset) {
      syncProcessCatalog(selectedDataset.processes || []);
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
      `${paused ? "暂停" : "继续"}失败：${error.message}`;
    setStatus(app.status);
  }
}

async function stopSimulation() {
  if (
    app.status !== "running"
    && app.status !== "paused"
    && app.status !== "reoptimizing"
    && app.status !== "animating"
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
      `停止失败：${error.message}`;
    setStatus(app.status);
  } finally {
    elements.stopButton.textContent = "停止";
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
  if (!app.anomalyHandlingEnabled) {
    elements.autoMachineAnomaly.checked = false;
    return;
  }
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
    option.textContent = `M${machine.local_id ?? machine.id}`;
    option.title =
      `全局机器 ${machine.id} · 工艺 ${machine.stage_id ?? 1}`;
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
  if (!app.anomalyHandlingEnabled || app.status !== "running") {
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
syncAnomalyHandling({ enabled: false });
elements.scheduleTab.addEventListener(
  "click",
  () => setDashboardTab("schedule"),
);
elements.machineBoardTab.addEventListener(
  "click",
  () => setDashboardTab("machine-board"),
);
elements.materialBoardTab.addEventListener(
  "click",
  () => setDashboardTab("material-board"),
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
elements.monitorViewButton.addEventListener(
  "click",
  () => setActivePage("monitor"),
);
elements.modelTestViewButton.addEventListener(
  "click",
  () => setActivePage("model-test"),
);
elements.anomalyModelTab.addEventListener(
  "click",
  () => setModelTestTab("anomaly"),
);
elements.hlsModelTab.addEventListener(
  "click",
  () => setModelTestTab("hls"),
);
elements.constructionModelTab.addEventListener(
  "click",
  () => setModelTestTab("construction"),
);
elements.anomalyTestDatasetSelect.addEventListener("change", () => {
  const processId = Number(elements.anomalyTestDatasetSelect.value || 1);
  resetModelTestResult();
  setModelTestStatus("等待测试", "idle");
  void loadAnomalyTestContext(processId).catch((error) => {
    elements.anomalyTestModelName.textContent = "检测服务不可用";
    elements.anomalyTestModelArtifact.textContent = error.message;
  });
});
elements.anomalyTestMachineSelect.addEventListener("change", () => {
  updateAnomalyMachineTimeRange();
  resetModelTestResult();
  setModelTestStatus("等待测试", "idle");
});
elements.runAnomalyModelTestButton.addEventListener(
  "click",
  runAnomalyModelTest,
);
elements.runHlsModelTestButton.addEventListener(
  "click",
  runHlsModelTest,
);
elements.constructionTestDatasetSelect.addEventListener("change", () => {
  resetModelTestResult();
  setModelTestStatus("等待测试", "idle");
});
elements.constructionTestMethodSelect.addEventListener("change", () => {
  resetModelTestResult();
  setModelTestStatus("等待测试", "idle");
});
elements.runConstructionModelTestButton.addEventListener(
  "click",
  runConstructionModelTest,
);
elements.clearModelTestResultButton.addEventListener("click", () => {
  resetModelTestResult();
  setModelTestStatus("等待测试", "idle");
});
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
  const dataset = app.datasetCatalog.find(
    (item) => item.id === elements.datasetSelect.value,
  );
  if (dataset) {
    syncProcessCatalog(dataset.processes || []);
  }
  clearDetectionStream();
});
elements.speedSelect.addEventListener("change", changeSpeed);
elements.displaySelect.addEventListener("change", changeDisplayPercent);
window.addEventListener("resize", () => {
  resizeMachineCharts();
  resizeHlsGanttChart();
  resizeAnomalyTestCharts();
});
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
void loadConstructionMethods();
