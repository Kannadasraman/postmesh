"use client";

import {
  Check,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

type Topic = {
  id: string;
  name: string;
  keywords: string[];
  active: boolean;
  research_frequency: string;
  created_at: string;
  updated_at: string;
};

type ResearchItem = {
  id: string;
  topic_id: string;
  title: string;
  url: string;
  source: string;
  summary: string | null;
  published_at: string | null;
  relevance_score: number;
  created_at: string;
};

type Platform = "linkedin" | "x" | "facebook" | "blog";

type ContentDraft = {
  id: string;
  topic_id: string;
  research_item_id: string;
  platform: string;
  status: "draft" | "approved" | "rejected";
  content: string;
  model_name: string;
  created_at: string;
  updated_at: string;
};

const PLATFORM_LABELS: Record<Platform, string> = {
  linkedin: "LinkedIn",
  x: "X",
  facebook: "Facebook",
  blog: "Blog",
};

export default function Home() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicName, setTopicName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [creatingTopic, setCreatingTopic] = useState(false);
  const [researchingTopicId, setResearchingTopicId] = useState<string | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [researchResults, setResearchResults] = useState<Record<string, ResearchItem[]>>({});
  const [platformByResearchId, setPlatformByResearchId] = useState<Record<string, Platform>>({});
  const [generatingResearchId, setGeneratingResearchId] = useState<string | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<ContentDraft | null>(null);
  const [draftContent, setDraftContent] = useState("");
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftSaved, setDraftSaved] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState<
    "approved" | "rejected" | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  async function loadTopics() {
    try {
      setError(null);
      const response = await fetch(`${API_URL}/api/v1/topics`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error("Failed to load topics");
      }
      const data: Topic[] = await response.json();
      setTopics(data);
    } catch (err) {
      console.error(err);
      setError("Unable to load topics. Check that the PostMesh API is running.");
    } finally {
      setLoadingTopics(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_URL}/api/v1/topics`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load topics");
        }
        return response.json() as Promise<Topic[]>;
      })
      .then((data) => {
        if (!cancelled) {
          setTopics(data);
        }
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) {
          setError("Unable to load topics. Check that the PostMesh API is running.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingTopics(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function createTopic(event: FormEvent) {
    event.preventDefault();

    if (!topicName.trim()) {
      return;
    }

    try {
      setCreatingTopic(true);
      setError(null);

      const parsedKeywords = keywords
        .split(",")
        .map((keyword) => keyword.trim())
        .filter(Boolean);

      const response = await fetch(`${API_URL}/api/v1/topics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: topicName.trim(),
          keywords: parsedKeywords,
          active: true,
          research_frequency: "daily",
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to create topic");
      }

      setTopicName("");
      setKeywords("");
      await loadTopics();
    } catch (err) {
      console.error(err);
      setError("Unable to create topic.");
    } finally {
      setCreatingTopic(false);
    }
  }

  async function deleteTopic(topicId: string) {
    try {
      setError(null);

      const response = await fetch(`${API_URL}/api/v1/topics/${topicId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to delete topic");
      }

      setTopics((current) => current.filter((topic) => topic.id !== topicId));

      setResearchResults((current) => {
        const next = { ...current };
        delete next[topicId];
        return next;
      });

      if (selectedTopicId === topicId) {
        setSelectedTopicId(null);
        setSelectedDraft(null);
        setDraftContent("");
      }
    } catch (err) {
      console.error(err);
      setError("Unable to delete topic.");
    }
  }

  async function runResearch(topic: Topic) {
    try {
      setError(null);
      setResearchingTopicId(topic.id);
      setSelectedTopicId(topic.id);
      setSelectedDraft(null);
      setDraftContent("");

      const response = await fetch(
        `${API_URL}/api/v1/topics/${topic.id}/research`,
        { method: "POST" },
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Research request failed");
      }

      const data: ResearchItem[] = await response.json();

      setResearchResults((current) => ({
        ...current,
        [topic.id]: data,
      }));
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Unable to research this topic.");
    } finally {
      setResearchingTopicId(null);
    }
  }

  async function showSavedResearch(topic: Topic) {
    try {
      setError(null);
      setSelectedTopicId(topic.id);
      setSelectedDraft(null);
      setDraftContent("");

      const response = await fetch(
        `${API_URL}/api/v1/topics/${topic.id}/research`,
        { cache: "no-store" },
      );

      if (!response.ok) {
        throw new Error("Unable to load saved research.");
      }

      const data: ResearchItem[] = await response.json();

      setResearchResults((current) => ({
        ...current,
        [topic.id]: data,
      }));
    } catch (err) {
      console.error(err);
      setError("Unable to load saved research.");
    }
  }

  async function generateDraft(item: ResearchItem) {
    const platform = platformByResearchId[item.id] || "linkedin";

    try {
      setError(null);
      setDraftSaved(false);
      setGeneratingResearchId(item.id);

      const response = await fetch(
        `${API_URL}/api/v1/research/${item.id}/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform }),
        },
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Unable to generate draft.");
      }

      const draft: ContentDraft = await response.json();
      setSelectedDraft(draft);
      setDraftContent(draft.content);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Unable to generate draft.");
    } finally {
      setGeneratingResearchId(null);
    }
  }

  async function saveDraft() {
    if (!selectedDraft || !draftContent.trim()) {
      return;
    }

    try {
      setError(null);
      setSavingDraft(true);
      setDraftSaved(false);

      const response = await fetch(
        `${API_URL}/api/v1/drafts/${selectedDraft.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            content: draftContent.trim(),
          }),
        },
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Unable to save draft.");
      }

      const updatedDraft: ContentDraft = await response.json();
      setSelectedDraft(updatedDraft);
      setDraftContent(updatedDraft.content);
      setDraftSaved(true);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Unable to save draft.");
    } finally {
      setSavingDraft(false);
    }
  }

  async function updateDraftStatus(
    nextStatus: "approved" | "rejected",
  ) {
    if (!selectedDraft) {
      return;
    }

    try {
      setError(null);
      setDraftSaved(false);
      setUpdatingStatus(nextStatus);

      const response = await fetch(
        `${API_URL}/api/v1/drafts/${selectedDraft.id}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: nextStatus,
          }),
        },
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.detail || `Unable to mark draft as ${nextStatus}.`,
        );
      }

      const updatedDraft: ContentDraft = await response.json();
      setSelectedDraft(updatedDraft);
      setDraftContent(updatedDraft.content);
    } catch (err) {
      console.error(err);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to update draft status.",
      );
    } finally {
      setUpdatingStatus(null);
    }
  }

  function statusBadgeClass(status: ContentDraft["status"]) {
    if (status === "approved") {
      return "bg-emerald-500/10 text-emerald-300";
    }

    if (status === "rejected") {
      return "bg-red-500/10 text-red-300";
    }

    return "bg-slate-800 text-slate-400";
  }

  function formatDate(value: string | null) {
    if (!value) {
      return "Unknown date";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "Unknown date";
    }

    return new Intl.DateTimeFormat("en", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  function scoreLabel(score: number) {
    return `${Math.round(score * 100)}% match`;
  }

  const selectedTopic = topics.find((topic) => topic.id === selectedTopicId);

  const selectedResearch =
    selectedTopicId !== null
      ? researchResults[selectedTopicId] || []
      : [];

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-7xl px-6 py-10">
        <header className="mb-10 flex flex-col gap-4 border-b border-slate-800 pb-8 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-500 text-slate-950">
                <Sparkles size={19} />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">PostMesh</h1>
            </div>

            <p className="text-sm text-slate-400">
              Discover relevant content, generate grounded drafts, approve them, and publish.
            </p>
          </div>

          <div className="rounded-full border border-slate-700 bg-slate-900 px-4 py-2 text-xs text-slate-400">
            MVP · AI Generation
          </div>
        </header>

        {error && (
          <div className="mb-6 rounded-xl border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <section className="grid gap-6 lg:grid-cols-[360px_1fr]">
          <div className="space-y-6">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
              <div className="mb-5">
                <h2 className="text-lg font-semibold">Create a topic</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Tell PostMesh what you want to monitor.
                </p>
              </div>

              <form onSubmit={createTopic} className="space-y-4">
                <div>
                  <label
                    htmlFor="topic"
                    className="mb-2 block text-sm font-medium text-slate-300"
                  >
                    Topic
                  </label>
                  <input
                    id="topic"
                    value={topicName}
                    onChange={(event) => setTopicName(event.target.value)}
                    placeholder="e.g. AI Agents"
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none transition placeholder:text-slate-600 focus:border-cyan-500"
                  />
                </div>

                <div>
                  <label
                    htmlFor="keywords"
                    className="mb-2 block text-sm font-medium text-slate-300"
                  >
                    Keywords
                  </label>
                  <input
                    id="keywords"
                    value={keywords}
                    onChange={(event) => setKeywords(event.target.value)}
                    placeholder="agentic AI, autonomous agents"
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none transition placeholder:text-slate-600 focus:border-cyan-500"
                  />
                  <p className="mt-2 text-xs text-slate-500">
                    Separate keywords with commas.
                  </p>
                </div>

                <button
                  type="submit"
                  disabled={creatingTopic || !topicName.trim()}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {creatingTopic ? (
                    <Loader2 size={17} className="animate-spin" />
                  ) : (
                    <Plus size={17} />
                  )}

                  {creatingTopic ? "Creating..." : "Add Topic"}
                </button>
              </form>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
              <h3 className="font-semibold">MVP pipeline</h3>

              <div className="mt-4 space-y-3 text-sm">
                <div className="flex items-center gap-3 text-cyan-300">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/10 text-xs">
                    1
                  </span>
                  Topics
                </div>

                <div className="flex items-center gap-3 text-cyan-300">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/10 text-xs">
                    2
                  </span>
                  Trending research
                </div>

                <div className="flex items-center gap-3 text-cyan-300">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/10 text-xs">
                    3
                  </span>
                  AI generation
                </div>

                <div className="flex items-center gap-3 text-slate-500">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 text-xs">
                    4
                  </span>
                  Approval & publishing
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Your topics</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    Run fresh research for any topic.
                  </p>
                </div>

                <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-400">
                  {topics.length} {topics.length === 1 ? "topic" : "topics"}
                </span>
              </div>

              {loadingTopics ? (
                <div className="flex items-center gap-2 py-10 text-sm text-slate-400">
                  <Loader2 size={18} className="animate-spin" />
                  Loading topics...
                </div>
              ) : topics.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 py-12 text-center">
                  <Search size={24} className="mx-auto mb-3 text-slate-600" />
                  <p className="text-sm text-slate-400">
                    Create your first topic to begin.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {topics.map((topic) => {
                    const isResearching = researchingTopicId === topic.id;
                    const savedCount = researchResults[topic.id]?.length;

                    return (
                      <div
                        key={topic.id}
                        className={`rounded-xl border p-4 transition ${
                          selectedTopicId === topic.id
                            ? "border-cyan-500/60 bg-cyan-500/5"
                            : "border-slate-800 bg-slate-950/60"
                        }`}
                      >
                        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                          <div className="min-w-0">
                            <div className="flex items-center gap-3">
                              <h3 className="truncate font-medium">{topic.name}</h3>
                              <span className="rounded-full border border-emerald-900 bg-emerald-950/60 px-2 py-0.5 text-[11px] text-emerald-400">
                                Active
                              </span>
                            </div>

                            <p className="mt-2 text-xs text-slate-500">
                              {topic.keywords.length > 0
                                ? topic.keywords.join(", ")
                                : "No additional keywords"}
                            </p>
                          </div>

                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void showSavedResearch(topic)}
                              className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:bg-slate-800"
                            >
                              Saved
                              {typeof savedCount === "number"
                                ? ` (${savedCount})`
                                : ""}
                            </button>

                            <button
                              type="button"
                              disabled={isResearching}
                              onClick={() => void runResearch(topic)}
                              className="flex items-center gap-2 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              {isResearching ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <RefreshCw size={14} />
                              )}

                              {isResearching
                                ? "Researching..."
                                : "Find Trending Content"}
                            </button>

                            <button
                              type="button"
                              onClick={() => void deleteTopic(topic.id)}
                              aria-label={`Delete ${topic.name}`}
                              className="rounded-lg border border-slate-800 p-2 text-slate-500 transition hover:border-red-900 hover:bg-red-950/30 hover:text-red-400"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
              <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Trending research</h2>
                  <p className="mt-1 text-sm text-slate-400">
                    {selectedTopic
                      ? `Results for ${selectedTopic.name}`
                      : "Choose a topic and run research."}
                  </p>
                </div>

                {selectedResearch.length > 0 && (
                  <span className="rounded-full bg-cyan-500/10 px-3 py-1 text-xs text-cyan-300">
                    {selectedResearch.length} results
                  </span>
                )}
              </div>

              {!selectedTopicId ? (
                <div className="rounded-xl border border-dashed border-slate-700 py-14 text-center">
                  <Search size={26} className="mx-auto mb-3 text-slate-600" />
                  <p className="text-sm text-slate-400">
                    Click Find Trending Content on a topic.
                  </p>
                </div>
              ) : researchingTopicId === selectedTopicId ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-slate-800 py-14">
                  <Loader2 size={28} className="mb-4 animate-spin text-cyan-400" />
                  <p className="font-medium">Researching the web...</p>
                  <p className="mt-1 text-sm text-slate-500">
                    Checking Google News and Hacker News.
                  </p>
                </div>
              ) : selectedResearch.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 py-14 text-center">
                  <p className="text-sm text-slate-400">
                    No saved research yet for this topic.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedResearch.map((item, index) => {
                    const platform =
                      platformByResearchId[item.id] || "linkedin";
                    const isGenerating =
                      generatingResearchId === item.id;

                    return (
                      <article
                        key={item.id}
                        className="rounded-xl border border-slate-800 bg-slate-950/60 p-5"
                      >
                        <div className="flex gap-4">
                          <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-xs font-semibold text-slate-400 sm:flex">
                            {index + 1}
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="mb-3 flex flex-wrap items-center gap-2">
                              <span className="rounded-full bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-300">
                                {item.source}
                              </span>

                              <span className="rounded-full bg-cyan-500/10 px-2.5 py-1 text-[11px] font-medium text-cyan-300">
                                {scoreLabel(item.relevance_score)}
                              </span>

                              <span className="text-xs text-slate-600">
                                {formatDate(item.published_at)}
                              </span>
                            </div>

                            <h3 className="text-base font-semibold leading-6 text-slate-100">
                              {item.title}
                            </h3>

                            {item.summary && item.summary !== item.title && (
                              <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-400">
                                {item.summary}
                              </p>
                            )}

                            <div className="mt-4 flex flex-wrap items-center gap-3">
                              <a
                                href={item.url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 transition hover:text-cyan-300"
                              >
                                Open source
                                <ExternalLink size={13} />
                              </a>

                              <select
                                value={platform}
                                onChange={(event) =>
                                  setPlatformByResearchId((current) => ({
                                    ...current,
                                    [item.id]: event.target.value as Platform,
                                  }))
                                }
                                className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-500"
                              >
                                {Object.entries(PLATFORM_LABELS).map(
                                  ([value, label]) => (
                                    <option key={value} value={value}>
                                      {label}
                                    </option>
                                  ),
                                )}
                              </select>

                              <button
                                type="button"
                                disabled={isGenerating}
                                onClick={() => void generateDraft(item)}
                                className="inline-flex items-center gap-2 rounded-lg border border-cyan-700 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {isGenerating ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <WandSparkles size={13} />
                                )}

                                {isGenerating
                                  ? "Generating..."
                                  : "Generate Post"}
                              </button>
                            </div>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>

            {selectedDraft && (
              <section className="rounded-2xl border border-cyan-900/60 bg-slate-900/80 p-6">
                <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-semibold">Draft preview</h2>

                      <span className="rounded-full bg-cyan-500/10 px-2.5 py-1 text-[11px] font-medium text-cyan-300">
                        {PLATFORM_LABELS[
                          selectedDraft.platform as Platform
                        ] || selectedDraft.platform}
                      </span>

                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${statusBadgeClass(
                          selectedDraft.status,
                        )}`}
                      >
                        {selectedDraft.status}
                      </span>
                    </div>

                    <p className="mt-1 text-xs text-slate-500">
                      Generated with {selectedDraft.model_name}
                    </p>
                  </div>

                  {draftSaved && (
                    <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                      <Check size={14} />
                      Saved
                    </div>
                  )}
                </div>

                {selectedDraft.status === "approved" && (
                  <div className="mb-4 rounded-xl border border-emerald-900/60 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">
                    Approved — this draft is ready for the publishing milestone.
                  </div>
                )}

                {selectedDraft.status === "rejected" && (
                  <div className="mb-4 rounded-xl border border-red-900/60 bg-red-950/30 px-4 py-3 text-sm text-red-300">
                    Rejected — edit and save the draft to return it to review.
                  </div>
                )}

                <textarea
                  value={draftContent}
                  onChange={(event) => {
                    setDraftContent(event.target.value);
                    setDraftSaved(false);
                  }}
                  rows={12}
                  className="w-full resize-y rounded-xl border border-slate-700 bg-slate-950 px-4 py-4 text-sm leading-7 text-slate-200 outline-none transition focus:border-cyan-500"
                />

                <div className="mt-4 flex flex-col gap-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-slate-500">
                      {selectedDraft.status === "draft"
                        ? "Edit and save before approving or rejecting."
                        : "If you edit this reviewed draft and save it, PostMesh automatically returns it to draft status."}
                    </p>

                    <button
                      type="button"
                      disabled={savingDraft || !draftContent.trim()}
                      onClick={() => void saveDraft()}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingDraft ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Save size={15} />
                      )}

                      {savingDraft ? "Saving..." : "Save Draft"}
                    </button>
                  </div>

                  <div className="flex flex-col gap-3 border-t border-slate-800 pt-4 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-slate-500">
                      Review status controls whether the draft is ready for publishing.
                    </p>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={
                          updatingStatus !== null ||
                          selectedDraft.status === "rejected"
                        }
                        onClick={() => void updateDraftStatus("rejected")}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-900 bg-red-950/30 px-4 py-2 text-sm font-semibold text-red-300 transition hover:bg-red-950/60 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {updatingStatus === "rejected" ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <X size={15} />
                        )}

                        {updatingStatus === "rejected"
                          ? "Rejecting..."
                          : selectedDraft.status === "rejected"
                            ? "Rejected"
                            : "Reject"}
                      </button>

                      <button
                        type="button"
                        disabled={
                          updatingStatus !== null ||
                          selectedDraft.status === "approved"
                        }
                        onClick={() => void updateDraftStatus("approved")}
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {updatingStatus === "approved" ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <Check size={15} />
                        )}

                        {updatingStatus === "approved"
                          ? "Approving..."
                          : selectedDraft.status === "approved"
                            ? "Approved"
                            : "Approve"}
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
