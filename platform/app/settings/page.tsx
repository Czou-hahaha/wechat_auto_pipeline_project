"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Database, Tags, Save, Plus, Pencil, Trash2, Clock, X, ShieldCheck } from "lucide-react";
import { CardStatic } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  KEYWORD_SECTIONS,
  languageLabel,
  type PromptContractPayload,
  type PromptPreviewPayload,
  sourceHealthKey,
  type DataSourceHealthEntry,
  type DataSourceHealthResponse,
  type DataSourceRecord,
  type KeywordsConfig,
  type SourceCandidateRecord,
  type FeedbackPolicyRecommendation,
} from "@/types/config";
import type { ScheduleConfig, ScheduleJob } from "@/types/schedule";
import { newScheduleJob } from "@/types/schedule";

type Tab = "sources" | "keywords" | "schedule" | "prompts";

const TIMEZONE_OPTIONS = [
  "Asia/Shanghai",
  "Asia/Hong_Kong",
  "Asia/Tokyo",
  "UTC",
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 60 }, (_, i) => i);

const EMPTY_SOURCE: DataSourceRecord = {
  id: "",
  name: "",
  kind: "web",
  value: "",
  language: "zh",
  ingest_mode: "html_list",
  list_monitor_url: "",
  region: "CN",
};

function ingestModeLabel(mode?: string): string {
  return mode === "rss" ? "RSS" : "栏目页";
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("sources");
  const [sources, setSources] = useState<DataSourceRecord[]>([]);
  const [keywords, setKeywords] = useState<KeywordsConfig>({});
  const [schedule, setSchedule] = useState<ScheduleConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [scheduleFeedback, setScheduleFeedback] = useState<{
    type: "ok" | "err";
    text: string;
  } | null>(null);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<DataSourceRecord | null>(null);
  const [healthMap, setHealthMap] = useState<Record<string, DataSourceHealthEntry>>({});
  const [healthAlerts, setHealthAlerts] = useState<DataSourceHealthResponse["alerts"]>([]);
  const [lastHealthScan, setLastHealthScan] = useState("");
  const [validating, setValidating] = useState(false);
  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  const [scanningHealth, setScanningHealth] = useState(false);
  const [candidates, setCandidates] = useState<SourceCandidateRecord[]>([]);
  const [discoveringCandidates, setDiscoveringCandidates] = useState(false);
  const [probingHost, setProbingHost] = useState<string>("");
  const [policyRec, setPolicyRec] = useState<FeedbackPolicyRecommendation | null>(null);
  const [policyOverrides, setPolicyOverrides] = useState<Record<string, unknown>>({});
  const [recomputingPolicy, setRecomputingPolicy] = useState(false);
  const [applyingPolicy, setApplyingPolicy] = useState(false);
  const [lastBackupPath, setLastBackupPath] = useState("");
  const [policyMsg, setPolicyMsg] = useState<{ type: "ok" | "err"; text: string } | null>(
    null,
  );
  const [promptContract, setPromptContract] = useState<PromptContractPayload["contract"] | null>(
    null,
  );
  const [promptPreview, setPromptPreview] = useState<PromptPreviewPayload | null>(null);
  const [loadingPromptPreview, setLoadingPromptPreview] = useState(false);
  const [promptObjectiveDraft, setPromptObjectiveDraft] = useState("");
  const [promptRulesDraft, setPromptRulesDraft] = useState("");
  const [promptSoftRulesDraft, setPromptSoftRulesDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const [
        dsRes,
        kwRes,
        schRes,
        healthRes,
        candidatesRes,
        policyRes,
        promptContractRes,
      ] = await Promise.all([
        fetch("/api/config/data-sources"),
        fetch("/api/config/keywords"),
        fetch("/api/config/schedule"),
        fetch("/api/config/data-sources/health"),
        fetch("/api/sources/candidates"),
        fetch("/api/feedback/policy"),
        fetch("/api/prompts/contract"),
      ]);
      const ds = await dsRes.json();
      const kw = await kwRes.json();
      const sch = await schRes.json();
      const health = (await healthRes.json()) as DataSourceHealthResponse;
      const candidateBody = (await candidatesRes.json()) as {
        items?: SourceCandidateRecord[];
      };
      const policyBody = (await policyRes.json()) as {
        recommendation?: FeedbackPolicyRecommendation;
        overrides?: Record<string, unknown>;
      };
      const promptContractBody = (await promptContractRes.json()) as PromptContractPayload;
      if (!schRes.ok) {
        throw new Error(
          (sch as { error?: string }).error || `schedule HTTP ${schRes.status}`,
        );
      }
      setSources(ds.items || []);
      setHealthMap(health.sources || {});
      setHealthAlerts(health.alerts || []);
      setLastHealthScan(health.last_full_scan_at || "");
      setCandidates(candidateBody.items || []);
      setPolicyRec(policyBody.recommendation || null);
      setPolicyOverrides(policyBody.overrides || {});
      setPromptContract(promptContractBody.contract || null);
      const rawKw = (kw.data || {}) as KeywordsConfig;
      setKeywords({
        chinese_keywords: rawKw.chinese_keywords || [],
        english_keywords: rawKw.english_keywords || [],
      });
      const schData = sch as ScheduleConfig;
      setSchedule({
        ...schData,
        jobs: schData.jobs?.length
          ? schData.jobs
          : [
              { id: "job_morning", label: "早间采集", hour: 8, minute: 0 },
              { id: "job_evening", label: "晚间采集", hour: 20, minute: 0 },
            ],
        article_age: schData.article_age ?? {
          unit: "hours",
          value: schData.article_age_hours ?? 14,
        },
        article_age_limit_enabled: schData.article_age_limit_enabled ?? true,
        article_age_hours: schData.article_age_hours ?? 14,
      });
    } catch {
      setMessage({ type: "err", text: "加载失败，请刷新页面" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!promptContract) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPromptObjectiveDraft(promptContract.objective || "");
    setPromptRulesDraft((promptContract.hard_rules || []).join("\n"));
    setPromptSoftRulesDraft((promptContract.soft_rules || []).join("\n"));
  }, [promptContract]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      if (tab === "sources") {
        const res = await fetch("/api/config/data-sources", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(sources),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        setSources(data.items || sources);
        setMessage({ type: "ok", text: "数据源已保存" });
      } else if (tab === "keywords") {
        const res = await fetch("/api/config/keywords", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(keywords),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        setKeywords(data.data || keywords);
        setMessage({ type: "ok", text: "关键词已保存" });
      } else if (tab === "schedule" && schedule) {
        const res = await fetch("/api/config/schedule", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enabled: schedule.enabled,
            timezone: schedule.timezone,
            jobs: schedule.jobs,
            article_age: schedule.article_age,
            article_age_limit_enabled: schedule.article_age_limit_enabled ?? true,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        const saved = data as ScheduleConfig;
        setSchedule(saved);
        const note =
          saved.schedulerNote ||
          saved.schedulerWarning ||
          (saved.scheduler?.state === "running"
            ? "定时调度已在后台运行"
            : "定时与采集窗口已保存");
        setScheduleFeedback({
          type: saved.schedulerWarning ? "err" : "ok",
          text: note,
        });
        setMessage(null);
      } else if (tab === "prompts") {
        const hard_rules = promptRulesDraft
          .split(/\n/)
          .map((x) => x.trim())
          .filter(Boolean);
        const soft_rules = promptSoftRulesDraft
          .split(/\n/)
          .map((x) => x.trim())
          .filter(Boolean);
        const res = await fetch("/api/prompts/contract", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            objective: promptObjectiveDraft.trim(),
            hard_rules,
            soft_rules,
          }),
        });
        const data = (await res.json()) as PromptContractPayload & { detail?: string };
        if (!res.ok || !data.contract) {
          throw new Error(data.detail || "Prompt Contract 保存失败");
        }
        setPromptContract(data.contract);
        setMessage({ type: "ok", text: "Prompt Contract 已保存" });
      }
    } catch (e) {
      setMessage({
        type: "err",
        text: e instanceof Error ? e.message : "保存失败",
      });
    } finally {
      setSaving(false);
    }
  }

  function openAdd() {
    setDraft({
      ...EMPTY_SOURCE,
      id: `src_${Date.now()}`,
      name: "新数据源",
    });
    setEditIndex(-1);
  }

  function openEdit(index: number) {
    setDraft({ ...sources[index] });
    setEditIndex(index);
  }

  async function commitDraft() {
    if (!draft || editIndex === null) return;
    const normalized: DataSourceRecord = {
      ...draft,
      kind: draft.kind || "web",
      rss:
        (draft.ingest_mode || "html_list") === "rss"
          ? (draft.rss || draft.list_monitor_url || "").trim()
          : draft.rss,
      rss_available: (draft.ingest_mode || "html_list") === "rss",
    };

    if (editIndex < 0) {
      setValidating(true);
      setValidateMsg("检查中…");
      try {
        const res = await fetch("/api/config/data-sources/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(normalized),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          setValidateMsg(data.message || data.detail || "验证未通过");
          return;
        }
        setSources((prev) => [...prev, normalized]);
        const key = sourceHealthKey(normalized);
        setHealthMap((prev) => ({
          ...prev,
          [key]: {
            key,
            source_id: normalized.id,
            name: normalized.name,
            status: "ok",
            message: data.message || "通过验证",
            checked_at: new Date().toISOString(),
            needs_attention: false,
          },
        }));
        setMessage({ type: "ok", text: "通过验证，已添加（请点击「保存配置」写入文件）" });
        setEditIndex(null);
        setDraft(null);
        setValidateMsg(null);
      } catch {
        setValidateMsg("验证请求失败，请确认 V4 BFF 已启动");
      } finally {
        setValidating(false);
      }
      return;
    }

    setSources((prev) =>
      prev.map((row, i) => (i === editIndex ? normalized : row)),
    );
    setEditIndex(null);
    setDraft(null);
    setValidateMsg(null);
  }

  async function runHealthScan() {
    setScanningHealth(true);
    setMessage(null);
    try {
      const res = await fetch("/api/config/data-sources/health", { method: "POST" });
      const data = (await res.json()) as DataSourceHealthResponse;
      if (!res.ok) throw new Error((data as { error?: string }).error || "扫描失败");
      setHealthMap(data.sources || {});
      setHealthAlerts(data.alerts || []);
      setLastHealthScan(data.last_full_scan_at || "");
      const n = data.summary?.needs_attention ?? data.alerts?.length ?? 0;
      setMessage({
        type: n > 0 ? "err" : "ok",
        text:
          n > 0
            ? `扫描完成：${n} 个数据源需处理（见下方提醒）`
            : "扫描完成：全部数据源可采集",
      });
    } catch (e) {
      setMessage({
        type: "err",
        text: e instanceof Error ? e.message : "健康扫描失败",
      });
    } finally {
      setScanningHealth(false);
    }
  }

  async function discoverSourceCandidates() {
    setDiscoveringCandidates(true);
    setMessage(null);
    try {
      const res = await fetch("/api/sources/discover", { method: "POST" });
      const data = (await res.json()) as { items?: SourceCandidateRecord[] };
      if (!res.ok) throw new Error("候选来源发现失败");
      setCandidates(data.items || []);
      setMessage({ type: "ok", text: "已刷新候选来源列表" });
    } catch (e) {
      setMessage({
        type: "err",
        text: e instanceof Error ? e.message : "候选来源发现失败",
      });
    } finally {
      setDiscoveringCandidates(false);
    }
  }

  async function probeSourceCandidate(host: string) {
    setProbingHost(host);
    setMessage(null);
    try {
      const res = await fetch(
        `/api/sources/candidates/${encodeURIComponent(host)}/probe`,
        { method: "POST" },
      );
      const data = (await res.json()) as { item?: SourceCandidateRecord };
      if (!res.ok || !data.item) throw new Error("探测失败");
      setCandidates((prev) =>
        prev.map((row) => (row.host === host ? data.item! : row)),
      );
      setMessage({
        type: "ok",
        text: `${host} 探测完成：${data.item.status}`,
      });
    } catch (e) {
      setMessage({
        type: "err",
        text: e instanceof Error ? e.message : "探测失败",
      });
    } finally {
      setProbingHost("");
    }
  }

  async function recomputeFeedbackPolicy() {
    setRecomputingPolicy(true);
    setPolicyMsg(null);
    try {
      const res = await fetch("/api/feedback/policy/recompute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ windowDays: 14 }),
      });
      const data = (await res.json()) as {
        recommendation?: FeedbackPolicyRecommendation;
      };
      if (!res.ok || !data.recommendation) throw new Error("策略重算失败");
      setPolicyRec(data.recommendation);
      setPolicyMsg({ type: "ok", text: "已生成最新反馈策略建议" });
    } catch (e) {
      setPolicyMsg({
        type: "err",
        text: e instanceof Error ? e.message : "策略重算失败",
      });
    } finally {
      setRecomputingPolicy(false);
    }
  }

  async function applyFeedbackPolicy() {
    if (!policyRec?.id) return;
    setApplyingPolicy(true);
    setPolicyMsg(null);
    try {
      const res = await fetch("/api/feedback/policy/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recommendationId: policyRec.id,
          confirmToken: "APPLY_FEEDBACK_POLICY",
        }),
      });
      const data = (await res.json()) as {
        applied_overrides?: Record<string, unknown>;
        backup_path?: string;
      };
      if (!res.ok || !data.applied_overrides) {
        throw new Error("策略应用失败（可能被安全机制拦截）");
      }
      setPolicyOverrides(data.applied_overrides);
      setLastBackupPath(data.backup_path || "");
      setPolicyMsg({ type: "ok", text: "策略已应用，将影响后续 QA/筛选执行" });
    } catch (e) {
      setPolicyMsg({
        type: "err",
        text: e instanceof Error ? e.message : "策略应用失败",
      });
    } finally {
      setApplyingPolicy(false);
    }
  }

  async function rollbackFeedbackPolicy() {
    if (!lastBackupPath) return;
    setApplyingPolicy(true);
    setPolicyMsg(null);
    try {
      const res = await fetch("/api/feedback/policy/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backupPath: lastBackupPath }),
      });
      const data = (await res.json()) as { restored_overrides?: Record<string, unknown> };
      if (!res.ok || !data.restored_overrides) throw new Error("回滚失败");
      setPolicyOverrides(data.restored_overrides);
      setPolicyMsg({ type: "ok", text: "策略已回滚到上一个安全快照" });
    } catch (e) {
      setPolicyMsg({
        type: "err",
        text: e instanceof Error ? e.message : "回滚失败",
      });
    } finally {
      setApplyingPolicy(false);
    }
  }

  async function loadPromptPreview() {
    setLoadingPromptPreview(true);
    setPolicyMsg(null);
    try {
      const res = await fetch("/api/prompts/preview");
      const data = (await res.json()) as PromptPreviewPayload;
      if (!res.ok) throw new Error("Prompt 预览加载失败");
      setPromptPreview(data);
      setPolicyMsg({ type: "ok", text: "Prompt Preview 已加载（管理员视图）" });
    } catch (e) {
      setPolicyMsg({
        type: "err",
        text: e instanceof Error ? e.message : "Prompt 预览加载失败",
      });
    } finally {
      setLoadingPromptPreview(false);
    }
  }

  async function acknowledgeAlert(key: string) {
    try {
      const res = await fetch("/api/config/data-sources/health/acknowledge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, note: "用户确认已更换或已处理" }),
      });
      const data = (await res.json()) as DataSourceHealthResponse & { ok?: boolean };
      if (!res.ok) throw new Error("确认失败");
      setHealthMap(data.sources || {});
      setHealthAlerts(data.alerts || []);
    } catch {
      setMessage({ type: "err", text: "无法标记已处理" });
    }
  }

  function removeSource(index: number) {
    if (!confirm(`确定删除「${sources[index]?.name}」？`)) return;
    setSources((prev) => prev.filter((_, i) => i !== index));
  }

  function setKeywordList(key: keyof KeywordsConfig, text: string) {
    const list = text
      .split(/[,，\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    setKeywords((prev) => ({ ...prev, [key]: list }));
  }

  return (
    <motion.div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">采集配置</h1>
        <p className="mt-1 text-sm text-zinc-700">
          配置数据源、检索词与定时策略；保存后点击「开始采集搜索」即按此配置入库。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <TabButton active={tab === "sources"} onClick={() => setTab("sources")} icon={Database}>
          数据源
        </TabButton>
        <TabButton active={tab === "keywords"} onClick={() => setTab("keywords")} icon={Tags}>
          关键词
        </TabButton>
        <TabButton
          active={tab === "schedule"}
          onClick={() => {
            setTab("schedule");
            setMessage(null);
          }}
          icon={Clock}
        >
          定时任务
        </TabButton>
        <TabButton
          active={tab === "prompts"}
          onClick={() => {
            setTab("prompts");
            setMessage(null);
          }}
          icon={ShieldCheck}
        >
          Prompts
        </TabButton>
        <button
          type="button"
          onClick={save}
          disabled={saving || loading}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm text-white hover:bg-sky-400 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "保存中…" : "保存配置"}
        </button>
      </div>

      {message && (
        <p
          className={cn(
            "text-sm",
            message.type === "ok" ? "text-emerald-700" : "text-rose-700",
          )}
        >
          {message.text}
        </p>
      )}

      {loading ? (
        <Skeleton className="h-96" />
      ) : tab === "sources" ? (
        <SourcesTable
          sources={sources}
          healthMap={healthMap}
          healthAlerts={healthAlerts}
          lastHealthScan={lastHealthScan}
          scanningHealth={scanningHealth}
          candidates={candidates}
          discoveringCandidates={discoveringCandidates}
          probingHost={probingHost}
          policyRec={policyRec}
          policyOverrides={policyOverrides}
          policyMsg={policyMsg}
          recomputingPolicy={recomputingPolicy}
          applyingPolicy={applyingPolicy}
          lastBackupPath={lastBackupPath}
          promptContract={promptContract}
          promptPreview={promptPreview}
          loadingPromptPreview={loadingPromptPreview}
          onScanHealth={runHealthScan}
          onDiscoverCandidates={discoverSourceCandidates}
          onProbeCandidate={probeSourceCandidate}
          onRecomputePolicy={recomputeFeedbackPolicy}
          onApplyPolicy={applyFeedbackPolicy}
          onRollbackPolicy={rollbackFeedbackPolicy}
          onLoadPromptPreview={loadPromptPreview}
          onAckAlert={acknowledgeAlert}
          onAdd={openAdd}
          onEdit={openEdit}
          onRemove={removeSource}
        />
      ) : tab === "keywords" ? (
        <KeywordsEditor keywords={keywords} onChange={setKeywordList} />
      ) : tab === "schedule" && schedule ? (
        <ScheduleEditor
          schedule={schedule}
          onChange={setSchedule}
          feedback={scheduleFeedback}
        />
      ) : tab === "prompts" ? (
        <PromptEditor
          promptContract={promptContract}
          promptObjectiveDraft={promptObjectiveDraft}
          promptRulesDraft={promptRulesDraft}
          promptSoftRulesDraft={promptSoftRulesDraft}
          promptPreview={promptPreview}
          loadingPromptPreview={loadingPromptPreview}
          onChangeObjective={setPromptObjectiveDraft}
          onChangeRules={setPromptRulesDraft}
          onChangeSoftRules={setPromptSoftRulesDraft}
          onLoadPreview={loadPromptPreview}
        />
      ) : null}

      {draft && editIndex !== null && (
        <SourceEditModal
          draft={draft}
          onChange={setDraft}
          onClose={() => {
            setEditIndex(null);
            setDraft(null);
          }}
          onConfirm={() => void commitDraft()}
          isNew={editIndex < 0}
          validating={validating}
          validateMsg={validateMsg}
        />
      )}
    </motion.div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
        active
          ? "border-sky-500/40 bg-sky-500/10 text-sky-700"
          : "border-zinc-200 text-zinc-700 hover:text-zinc-700",
      )}
    >
      <Icon className="h-4 w-4" />
      {children}
    </button>
  );
}

function healthStatusBadge(entry?: DataSourceHealthEntry) {
  const status = entry?.status || "unknown";
  if (status === "checking") {
    return (
      <Badge variant="muted" className="border-amber-500/40 text-amber-800">
        检查中
      </Badge>
    );
  }
  if (status === "ok") {
    return (
      <Badge variant="muted" className="border-emerald-500/40 text-emerald-700">
        通过验证
      </Badge>
    );
  }
  if (status === "failed") {
    return (
      <Badge variant="muted" className="border-rose-500/40 text-rose-700">
        不可采集
      </Badge>
    );
  }
  return (
    <Badge variant="muted" className="text-zinc-700">
      未检测
    </Badge>
  );
}

function SourcesTable({
  sources,
  healthMap,
  healthAlerts,
  lastHealthScan,
  scanningHealth,
  candidates,
  discoveringCandidates,
  probingHost,
  policyRec,
  policyOverrides,
  policyMsg,
  recomputingPolicy,
  applyingPolicy,
  lastBackupPath,
  promptContract,
  promptPreview,
  loadingPromptPreview,
  onScanHealth,
  onDiscoverCandidates,
  onProbeCandidate,
  onRecomputePolicy,
  onApplyPolicy,
  onRollbackPolicy,
  onLoadPromptPreview,
  onAckAlert,
  onAdd,
  onEdit,
  onRemove,
}: {
  sources: DataSourceRecord[];
  healthMap: Record<string, DataSourceHealthEntry>;
  healthAlerts: DataSourceHealthResponse["alerts"];
  lastHealthScan: string;
  scanningHealth: boolean;
  candidates: SourceCandidateRecord[];
  discoveringCandidates: boolean;
  probingHost: string;
  policyRec: FeedbackPolicyRecommendation | null;
  policyOverrides: Record<string, unknown>;
  policyMsg: { type: "ok" | "err"; text: string } | null;
  recomputingPolicy: boolean;
  applyingPolicy: boolean;
  lastBackupPath: string;
  promptContract: PromptContractPayload["contract"] | null;
  promptPreview: PromptPreviewPayload | null;
  loadingPromptPreview: boolean;
  onScanHealth: () => void;
  onDiscoverCandidates: () => void;
  onProbeCandidate: (host: string) => void;
  onRecomputePolicy: () => void;
  onApplyPolicy: () => void;
  onRollbackPolicy: () => void;
  onLoadPromptPreview: () => void;
  onAckAlert: (key: string) => void;
  onAdd: () => void;
  onEdit: (i: number) => void;
  onRemove: (i: number) => void;
}) {
  return (
    <CardStatic className="overflow-hidden p-0">
      {healthAlerts && healthAlerts.length > 0 && (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <p className="font-medium">有 {healthAlerts.length} 个数据源无法采集，请更换栏目/RSS 或确认已自行更换：</p>
          <ul className="mt-2 space-y-2">
            {healthAlerts.map((a) => (
              <li key={a.key} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span>
                  <strong>{a.name || a.source_id}</strong>
                  {a.message ? ` — ${a.message}` : ""}
                </span>
                <button
                  type="button"
                  onClick={() => onAckAlert(a.key)}
                  className="rounded-md border border-rose-300 px-2 py-1 text-rose-800 hover:bg-rose-100"
                >
                  我已更换 / 已处理
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3">
        <span className="text-sm text-zinc-700">
          共 {sources.length} 个数据源
          {lastHealthScan ? (
            <span className="ml-2 text-zinc-700">
              上次周检 {new Date(lastHealthScan).toLocaleString("zh-CN")}
            </span>
          ) : null}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void onScanHealth()}
            disabled={scanningHealth}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-xs text-zinc-700 hover:text-zinc-800 disabled:opacity-50"
          >
            {scanningHealth ? "扫描中…" : "立即检测全部"}
          </button>
          <button
            type="button"
            onClick={onAdd}
            className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500/15 px-3 py-1.5 text-xs text-sky-700 hover:bg-sky-500/25"
          >
            <Plus className="h-3.5 w-3.5" />
            添加
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-[11px] uppercase tracking-wider text-zinc-700">
              <th className="px-4 py-2.5 font-medium">名称</th>
              <th className="px-4 py-2.5 font-medium">语言</th>
              <th className="px-4 py-2.5 font-medium">域名</th>
              <th className="px-4 py-2.5 font-medium">方式</th>
              <th className="px-4 py-2.5 font-medium">采集状态</th>
              <th className="px-4 py-2.5 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((row, i) => (
              <tr
                key={`${row.id}-${i}`}
                className="border-b border-zinc-100 hover:bg-zinc-50"
              >
                <td className="px-4 py-3 text-zinc-800">{row.name}</td>
                <td className="px-4 py-3">
                  <Badge
                    variant="muted"
                    className={
                      (row.language || "zh").startsWith("en")
                        ? "border-violet-500/30 text-violet-800"
                        : "border-amber-500/30 text-amber-800"
                    }
                  >
                    {languageLabel(row.language)}
                  </Badge>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-700">{row.value}</td>
                <td className="px-4 py-3 text-xs text-zinc-700">
                  {ingestModeLabel(row.ingest_mode)}
                </td>
                <td className="px-4 py-3">
                  {healthStatusBadge(healthMap[sourceHealthKey(row)])}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onEdit(i)}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 hover:text-sky-700"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      修改
                    </button>
                    <button
                      type="button"
                      onClick={() => onRemove(i)}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 hover:text-rose-700"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sources.length === 0 && (
        <p className="px-4 py-8 text-center text-sm text-zinc-700">暂无数据源，点击添加</p>
      )}

      <div className="border-t border-zinc-200 px-4 py-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-zinc-700">自动补源候选（V5 MVP）</p>
          <button
            type="button"
            onClick={onDiscoverCandidates}
            disabled={discoveringCandidates}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-1.5 text-xs text-zinc-700 hover:text-zinc-800 disabled:opacity-50"
          >
            {discoveringCandidates ? "发现中…" : "发现候选来源"}
          </button>
        </div>
        {candidates.length === 0 ? (
          <p className="text-xs text-zinc-700">暂无候选来源，可先点击“发现候选来源”。</p>
        ) : (
          <ul className="space-y-2">
            {candidates.slice(0, 8).map((c) => (
              <li
                key={c.host}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-zinc-800">
                    {c.host}
                  </p>
                  <p className="text-[11px] text-zinc-700">
                    命中 {c.mention_count} 次 · 状态 {c.status}
                    {c.ingest_mode ? ` · ${c.ingest_mode}` : ""}
                  </p>
                  {c.last_probe_message ? (
                    <p className="line-clamp-1 text-[11px] text-zinc-700">
                      {c.last_probe_message}
                    </p>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => onProbeCandidate(c.host)}
                  disabled={probingHost === c.host}
                  className="rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
                >
                  {probingHost === c.host ? "探测中…" : "探测"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-zinc-200 px-4 py-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="inline-flex items-center gap-2 text-sm text-zinc-700">
            <ShieldCheck className="h-4 w-4" />
            反馈策略闭环（安全机制）
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onRecomputePolicy}
              disabled={recomputingPolicy}
              className="rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
            >
              {recomputingPolicy ? "重算中…" : "重算建议"}
            </button>
            <button
              type="button"
              onClick={onApplyPolicy}
              disabled={applyingPolicy || !policyRec?.safe_to_apply}
              className="rounded-md bg-sky-500 px-2 py-1 text-xs text-white hover:bg-sky-400 disabled:opacity-50"
            >
              应用建议
            </button>
            <button
              type="button"
              onClick={onRollbackPolicy}
              disabled={applyingPolicy || !lastBackupPath}
              className="rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
            >
              回滚
            </button>
          </div>
        </div>
        {policyRec ? (
          <div className="space-y-1 text-xs text-zinc-700">
            <p>
              反馈窗口 {policyRec.window_days} 天 · 样本 {policyRec.feedback_total} 条 ·
              可应用 {policyRec.safe_to_apply ? "是" : "否"}
            </p>
            {policyRec.reasons?.length ? (
              <p>建议：{policyRec.reasons.join("；")}</p>
            ) : null}
            {policyRec.safety_notes?.length ? (
              <p className="text-amber-700">安全提示：{policyRec.safety_notes.join("；")}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-zinc-700">暂无策略建议，请先重算建议。</p>
        )}
        <p className="mt-1 text-xs text-zinc-700">
          当前覆盖参数：{JSON.stringify(policyOverrides || {}) || "{}"}
        </p>
        {policyMsg ? (
          <p className={cn("mt-1 text-xs", policyMsg.type === "ok" ? "text-emerald-700" : "text-rose-700")}>
            {policyMsg.text}
          </p>
        ) : null}
      </div>

      <div className="border-t border-zinc-200 px-4 py-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="inline-flex items-center gap-2 text-sm text-zinc-700">
            <ShieldCheck className="h-4 w-4" />
            Prompt Contract / Preview（管理员）
          </p>
          <button
            type="button"
            onClick={onLoadPromptPreview}
            disabled={loadingPromptPreview}
            className="rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            {loadingPromptPreview ? "加载中…" : "加载 Prompt Preview"}
          </button>
        </div>
        {promptContract ? (
          <div className="space-y-1 text-xs text-zinc-700">
            <p>目标：{promptContract.objective}</p>
            <p>硬规则：{(promptContract.hard_rules || []).join("；")}</p>
            <p>软规则：{(promptContract.soft_rules || []).join("；") || "（无）"}</p>
            <p>
              enforcement：
              {JSON.stringify(promptContract.enforcement || { hard: "must_pass_gate", soft: "rewrite_preference" })}
            </p>
            <p>运行参数：{JSON.stringify(promptContract.effective_runtime || {})}</p>
          </div>
        ) : (
          <p className="text-xs text-zinc-700">暂无 Prompt Contract 数据。</p>
        )}
        {promptPreview ? (
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">System Prompt Preview</p>
              <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-zinc-700">
                {promptPreview.systemPreview}
              </pre>
            </div>
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">User Prompt Template Preview</p>
              <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-zinc-700">
                {promptPreview.userTemplatePreview}
              </pre>
            </div>
          </div>
        ) : (
          <p className="mt-1 text-xs text-zinc-700">点击按钮加载管理员视图 Prompt Preview。</p>
        )}
      </div>
    </CardStatic>
  );
}

function SourceEditModal({
  draft,
  onChange,
  onClose,
  onConfirm,
  isNew,
  validating,
  validateMsg,
}: {
  draft: DataSourceRecord;
  onChange: (d: DataSourceRecord) => void;
  onClose: () => void;
  onConfirm: () => void;
  isNew: boolean;
  validating?: boolean;
  validateMsg?: string | null;
}) {
  const patch = (p: Partial<DataSourceRecord>) => onChange({ ...draft, ...p });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <CardStatic className="w-full max-w-lg space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-900">
            {isNew ? "添加数据源" : "修改数据源"}
          </h3>
          <button type="button" onClick={onClose} className="text-zinc-700 hover:text-zinc-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="名称">
            <input
              value={draft.name}
              onChange={(e) => patch({ name: e.target.value })}
              className="input-field"
            />
          </Field>
          <Field label="语言">
            <select
              value={draft.language || "zh"}
              onChange={(e) => patch({ language: e.target.value })}
              className="input-field"
            >
              <option value="zh">中文</option>
              <option value="en">英文</option>
            </select>
          </Field>
          <Field label="域名" className="sm:col-span-2">
            <input
              value={draft.value}
              onChange={(e) => patch({ value: e.target.value })}
              className="input-field font-mono text-xs"
              placeholder="example.com"
            />
          </Field>
          <Field label="采集方式">
            <select
              value={draft.ingest_mode || "html_list"}
              onChange={(e) => patch({ ingest_mode: e.target.value })}
              className="input-field"
            >
              <option value="html_list">栏目页</option>
              <option value="rss">RSS</option>
            </select>
          </Field>
          <Field label="区域">
            <select
              value={draft.region || "CN"}
              onChange={(e) => patch({ region: e.target.value })}
              className="input-field"
            >
              <option value="CN">中国</option>
              <option value="INTL">国际</option>
            </select>
          </Field>
          <Field label="栏目 / RSS 地址" className="sm:col-span-2">
            <input
              value={draft.list_monitor_url || draft.rss || ""}
              onChange={(e) => {
                const v = e.target.value;
                if ((draft.ingest_mode || "html_list") === "rss") {
                  patch({ list_monitor_url: v, rss: v, rss_available: true });
                } else {
                  patch({ list_monitor_url: v });
                }
              }}
              className="input-field font-mono text-xs"
            />
          </Field>
        </div>
        {isNew && validateMsg && (
          <p
            className={cn(
              "text-sm",
              validating
                ? "text-amber-300"
                : validateMsg.includes("通过")
                  ? "text-emerald-700"
                  : "text-rose-700",
            )}
          >
            {validateMsg}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-zinc-700 hover:text-zinc-800"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={validating}
            className="rounded-lg bg-sky-500 px-4 py-2 text-sm text-white hover:bg-sky-400 disabled:opacity-50"
          >
            {validating ? "检查中…" : isNew ? "验证并添加" : "确定"}
          </button>
        </div>
      </CardStatic>
    </div>
  );
}

function KeywordsEditor({
  keywords,
  onChange,
}: {
  keywords: KeywordsConfig;
  onChange: (key: keyof KeywordsConfig, text: string) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {KEYWORD_SECTIONS.map((section) => {
        const list = keywords[section.key] || [];
        return (
          <CardStatic key={section.key}>
            <h3 className="text-sm font-medium text-zinc-700">{section.label}</h3>
            <textarea
              value={list.join("\n")}
              onChange={(e) => onChange(section.key, e.target.value)}
              rows={8}
              placeholder="每行一个词"
              className="input-field mt-2 min-h-[140px] w-full resize-y font-mono text-xs"
            />
            <p className="mt-1 text-[10px] text-zinc-700">{list.length} 条</p>
          </CardStatic>
        );
      })}
    </div>
  );
}

function PromptEditor({
  promptContract,
  promptObjectiveDraft,
  promptRulesDraft,
  promptSoftRulesDraft,
  promptPreview,
  loadingPromptPreview,
  onChangeObjective,
  onChangeRules,
  onChangeSoftRules,
  onLoadPreview,
}: {
  promptContract: PromptContractPayload["contract"] | null;
  promptObjectiveDraft: string;
  promptRulesDraft: string;
  promptSoftRulesDraft: string;
  promptPreview: PromptPreviewPayload | null;
  loadingPromptPreview: boolean;
  onChangeObjective: (v: string) => void;
  onChangeRules: (v: string) => void;
  onChangeSoftRules: (v: string) => void;
  onLoadPreview: () => void;
}) {
  return (
    <div className="space-y-4">
      <CardStatic className="space-y-3">
        <h3 className="text-sm font-medium text-zinc-800">Prompt Contract（可编辑）</h3>
        <Field label="目标（objective）">
          <input
            value={promptObjectiveDraft}
            onChange={(e) => onChangeObjective(e.target.value)}
            className="input-field"
            placeholder="例如：多源事件通稿生成与事实性QA重写"
          />
        </Field>
        <Field label="硬规则（每行一条）">
          <textarea
            value={promptRulesDraft}
            onChange={(e) => onChangeRules(e.target.value)}
            rows={8}
            className="input-field min-h-[160px] w-full resize-y text-xs"
          />
        </Field>
        <Field label="软规则（每行一条，失败会触发重写倾向）">
          <textarea
            value={promptSoftRulesDraft}
            onChange={(e) => onChangeSoftRules(e.target.value)}
            rows={5}
            className="input-field min-h-[110px] w-full resize-y text-xs"
          />
        </Field>
        <p className="text-xs text-zinc-700">
          enforcement：hard=must_pass_gate，soft=rewrite_preference
        </p>
        <p className="text-xs text-zinc-700">
          当前运行参数：{JSON.stringify(promptContract?.effective_runtime || {})}
        </p>
      </CardStatic>

      <CardStatic className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-800">Prompt Preview（管理员）</h3>
          <button
            type="button"
            onClick={onLoadPreview}
            disabled={loadingPromptPreview}
            className="rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            {loadingPromptPreview ? "加载中…" : "加载预览"}
          </button>
        </div>
        {promptPreview ? (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">System</p>
              <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-zinc-700">
                {promptPreview.systemPreview}
              </pre>
            </div>
            <div className="rounded-md border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">User Template</p>
              <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-zinc-700">
                {promptPreview.userTemplatePreview}
              </pre>
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-700">点击加载预览查看当前模板。</p>
        )}
      </CardStatic>
    </div>
  );
}

function ScheduleJobsStatus({
  schedule,
  feedback,
}: {
  schedule: ScheduleConfig;
  feedback: { type: "ok" | "err"; text: string } | null;
}) {
  if (feedback) {
    return (
      <p
        className={cn(
          "text-xs leading-relaxed",
          feedback.type === "ok" ? "text-emerald-700/90" : "text-rose-700",
        )}
      >
        {feedback.text}
      </p>
    );
  }
  if (schedule.scheduler?.state === "running") {
    return (
      <p className="text-xs leading-relaxed text-emerald-700/90">
        调度已启动，将按下方时刻自动采集
        {schedule.scheduler.jobsSummary
          ? `（${schedule.scheduler.jobsSummary}）`
          : ""}
      </p>
    );
  }
  if (schedule.enabled) {
    return (
      <p className="text-xs text-amber-700/90">
        已启用定时采集，保存后将自动启动调度
      </p>
    );
  }
  return null;
}

function ScheduleEditor({
  schedule,
  onChange,
  feedback,
}: {
  schedule: ScheduleConfig;
  onChange: (s: ScheduleConfig) => void;
  feedback: { type: "ok" | "err"; text: string } | null;
}) {
  const patch = (p: Partial<ScheduleConfig>) => onChange({ ...schedule, ...p });

  function updateJob(index: number, job: Partial<ScheduleJob>) {
    const jobs = schedule.jobs.map((j, i) =>
      i === index ? { ...j, ...job } : j,
    );
    patch({ jobs });
  }

  function removeJob(index: number) {
    if (schedule.enabled && schedule.jobs.length <= 1) {
      alert("启用定时采集时请至少保留一个任务，或先关闭「启用定时采集」");
      return;
    }
    patch({ jobs: schedule.jobs.filter((_, i) => i !== index) });
  }

  function addJob() {
    patch({ jobs: [...schedule.jobs, newScheduleJob()] });
  }

  const ageLimitOn = schedule.article_age_limit_enabled ?? true;
  const ageUnit = schedule.article_age?.unit ?? "hours";
  const ageValue = schedule.article_age?.value ?? 14;

  return (
    <div className="space-y-4">
      <CardStatic>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-zinc-800">启用定时采集</h3>
            <p className="mt-1 text-xs text-zinc-700">
              开启并保存后，BFF 会自动启动 run-scheduler；关闭则停止后台调度
            </p>
          </div>
          <label className="relative inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={(e) => patch({ enabled: e.target.checked })}
              className="peer sr-only"
            />
            <span className="h-6 w-11 rounded-full bg-zinc-700 peer-checked:bg-sky-600 after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-5" />
          </label>
        </div>
      </CardStatic>

      <CardStatic className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-zinc-700">定时任务（每日执行时刻）</span>
          <button
            type="button"
            onClick={addJob}
            className="inline-flex items-center gap-1 rounded-lg bg-sky-500/15 px-2.5 py-1 text-xs text-sky-700 hover:bg-sky-500/25"
          >
            <Plus className="h-3.5 w-3.5" />
            添加
          </button>
        </div>
        <ScheduleJobsStatus schedule={schedule} feedback={feedback} />
        {schedule.jobs.length === 0 ? (
          <p className="text-xs text-zinc-700">暂无定时点（关闭「启用定时采集」时可留空）</p>
        ) : (
          <ul className="space-y-2">
            {schedule.jobs.map((job, i) => (
              <li
                key={job.id}
                className="flex flex-wrap items-center gap-2 border-b border-zinc-100 pb-2 last:border-0 last:pb-0"
              >
                <input
                  value={job.label}
                  onChange={(e) => updateJob(i, { label: e.target.value })}
                  className="input-field w-36 shrink-0 text-sm"
                  placeholder="名称"
                />
                <select
                  value={job.hour}
                  onChange={(e) =>
                    updateJob(i, { hour: Number(e.target.value) })
                  }
                  className="input-field w-[4.5rem] shrink-0 tabular-nums text-sm"
                  aria-label="时"
                >
                  {HOURS.map((h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, "0")} 时
                    </option>
                  ))}
                </select>
                <select
                  value={job.minute}
                  onChange={(e) =>
                    updateJob(i, { minute: Number(e.target.value) })
                  }
                  className="input-field w-[4.5rem] shrink-0 tabular-nums text-sm"
                  aria-label="分"
                >
                  {MINUTES.map((m) => (
                    <option key={m} value={m}>
                      {String(m).padStart(2, "0")} 分
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => removeJob(i)}
                  className="ml-auto inline-flex shrink-0 items-center gap-1 text-xs text-zinc-700 hover:text-rose-700"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardStatic>

      <CardStatic className="space-y-3 p-4">
        <p className="text-sm text-zinc-700">{schedule.summary}</p>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-xs text-zinc-700 shrink-0">时区</span>
          <select
            value={schedule.timezone}
            onChange={(e) => patch({ timezone: e.target.value })}
            className="input-field w-auto min-w-[10rem] max-w-full text-sm"
          >
            {TIMEZONE_OPTIONS.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-zinc-200 pt-3">
          <span className="text-xs text-zinc-700 shrink-0">采集时间范围</span>
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-zinc-700">
            <input
              type="checkbox"
              checked={ageLimitOn}
              onChange={(e) =>
                patch({ article_age_limit_enabled: e.target.checked })
              }
              className="rounded border-white/20"
            />
            限制发布时间
          </label>
          {ageLimitOn ? (
            <>
              <div className="flex shrink-0 rounded-lg border border-zinc-200 p-0.5">
                {(["hours", "days"] as const).map((u) => (
                  <button
                    key={u}
                    type="button"
                    onClick={() =>
                      patch({
                        article_age: {
                          unit: u,
                          value: ageValue || (u === "days" ? 3 : 24),
                        },
                      })
                    }
                    className={cn(
                      "rounded-md px-2 py-1 text-xs transition-colors",
                      ageUnit === u
                        ? "bg-sky-500/20 text-sky-700"
                        : "text-zinc-700 hover:text-zinc-700",
                    )}
                  >
                    {u === "hours" ? "小时" : "天"}
                  </button>
                ))}
              </div>
              <input
                type="number"
                min={1}
                max={ageUnit === "days" ? 365 : 8760}
                value={ageValue}
                onChange={(e) =>
                  patch({
                    article_age: {
                      unit: ageUnit,
                      value: Math.max(1, Number(e.target.value) || 1),
                    },
                  })
                }
                className="input-field w-16 shrink-0 tabular-nums text-sm"
              />
              <span className="text-xs text-zinc-700">
                {ageUnit === "days" ? "天" : "小时"}
              </span>
            </>
          ) : (
            <span className="text-xs text-zinc-700">已取消，不按发布时间过滤</span>
          )}
          {ageLimitOn && (
            <button
              type="button"
              onClick={() => patch({ article_age_limit_enabled: false })}
              className="text-xs text-zinc-700 hover:text-rose-700"
            >
              取消限制
            </button>
          )}
        </div>
      </CardStatic>
    </div>
  );
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1 block text-xs text-zinc-700">{label}</span>
      {children}
    </label>
  );
}
