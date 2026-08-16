"use client";

import { FormEvent, useEffect, useState } from "react";
import { Plus, Sparkles, Trash2, TrendingUp } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

type Topic = {
  id: string;
  name: string;
  keywords: string[];
  active: boolean;
  research_frequency: string;
  created_at: string;
  updated_at: string;
};

export default function Home() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadTopics() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(`${API_URL}/api/v1/topics`);

      if (!response.ok) {
        throw new Error("Unable to load topics");
      }

      const data: Topic[] = await response.json();
      setTopics(data);
    } catch {
      setError("Unable to connect to the PostMesh API.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTopics();
  }, []);

  async function createTopic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!name.trim()) {
      setError("Please enter a topic.");
      return;
    }

    try {
      setSaving(true);
      setError("");

      const response = await fetch(`${API_URL}/api/v1/topics`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: name.trim(),
          keywords: keywords
            .split(",")
            .map((keyword) => keyword.trim())
            .filter(Boolean),
          active: true,
          research_frequency: "daily",
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to create topic");
      }

      const topic: Topic = await response.json();

      setTopics((current) => [topic, ...current]);
      setName("");
      setKeywords("");
    } catch {
      setError("Unable to create the topic.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTopic(id: string) {
    try {
      const response = await fetch(`${API_URL}/api/v1/topics/${id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Unable to delete topic");
      }

      setTopics((current) => current.filter((topic) => topic.id !== id));
    } catch {
      setError("Unable to delete the topic.");
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-6xl px-6 py-8 lg:px-8">
        <header className="mb-12 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500">
              <Sparkles className="h-5 w-5" />
            </div>

            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                PostMesh
              </h1>
              <p className="text-sm text-slate-400">
                AI-powered social media content
              </p>
            </div>
          </div>

          <div className="hidden rounded-full border border-slate-800 bg-slate-900 px-4 py-2 text-sm text-slate-400 sm:block">
            Phase 1 · Topic Research
          </div>
        </header>

        <section className="mb-10">
          <div className="max-w-3xl">
            <p className="mb-3 text-sm font-medium text-indigo-400">
              CREATE BETTER CONTENT
            </p>

            <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">
              Tell PostMesh what you want to talk about.
            </h2>

            <p className="mt-4 text-lg leading-8 text-slate-400">
              PostMesh will find what is trending, turn it into social-ready
              content, and let you approve it before publishing.
            </p>
          </div>
        </section>

        <section className="mb-12 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl">
          <div className="mb-6 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-500/10 p-2 text-indigo-400">
              <Plus className="h-5 w-5" />
            </div>

            <div>
              <h3 className="font-semibold">Create a topic</h3>
              <p className="text-sm text-slate-400">
                Define what PostMesh should research.
              </p>
            </div>
          </div>

          <form onSubmit={createTopic} className="space-y-5">
            <div>
              <label
                htmlFor="topic"
                className="mb-2 block text-sm font-medium text-slate-300"
              >
                Topic
              </label>

              <input
                id="topic"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. AI Agents"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none transition placeholder:text-slate-600 focus:border-indigo-500"
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
                placeholder="AI agents, agentic AI, autonomous agents"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none transition placeholder:text-slate-600 focus:border-indigo-500"
              />

              <p className="mt-2 text-xs text-slate-500">
                Separate keywords with commas.
              </p>
            </div>

            {error && (
              <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
                {error}
              </div>
            )}

            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                type="submit"
                disabled={saving}
                className="flex items-center justify-center gap-2 rounded-xl bg-indigo-500 px-5 py-3 font-medium transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus className="h-4 w-4" />
                {saving ? "Creating..." : "Add Topic"}
              </button>

              <button
                type="button"
                disabled
                title="Trending research is coming in the next development phase"
                className="flex items-center justify-center gap-2 rounded-xl border border-slate-700 px-5 py-3 font-medium text-slate-500"
              >
                <TrendingUp className="h-4 w-4" />
                Find Trending Content
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs">
                  Next
                </span>
              </button>
            </div>
          </form>
        </section>

        <section>
          <div className="mb-5 flex items-end justify-between">
            <div>
              <h3 className="text-xl font-semibold">Your Topics</h3>
              <p className="mt-1 text-sm text-slate-400">
                Topics PostMesh will use for content research.
              </p>
            </div>

            <span className="text-sm text-slate-500">
              {topics.length} {topics.length === 1 ? "topic" : "topics"}
            </span>
          </div>

          {loading ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center text-slate-400">
              Loading topics...
            </div>
          ) : topics.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/50 p-10 text-center">
              <p className="font-medium">No topics yet</p>
              <p className="mt-1 text-sm text-slate-500">
                Add your first topic above to get started.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {topics.map((topic) => (
                <article
                  key={topic.id}
                  className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-3">
                        <h4 className="font-semibold">{topic.name}</h4>

                        {topic.active && (
                          <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                            Active
                          </span>
                        )}
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2">
                        {topic.keywords.map((keyword) => (
                          <span
                            key={keyword}
                            className="rounded-lg bg-slate-800 px-2.5 py-1 text-xs text-slate-300"
                          >
                            {keyword}
                          </span>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => deleteTopic(topic.id)}
                      className="rounded-lg p-2 text-slate-500 transition hover:bg-red-500/10 hover:text-red-400"
                      title={`Delete ${topic.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="mt-5 border-t border-slate-800 pt-4 text-xs text-slate-500">
                    Research frequency:{" "}
                    <span className="text-slate-400">
                      {topic.research_frequency}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}