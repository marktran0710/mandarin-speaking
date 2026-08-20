import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherBenchmarkPage from "./TeacherBenchmarkPage";

function statusBody(overrides: Record<string, unknown> = {}) {
  return {
    corpus: { downloaded: false, wav_count: 0, citation: "OMPAL corpus … CC BY 4.0." },
    job: {
      phase: "idle", running: false, done: 0, total: 0, message: "", error: null,
      downloaded_bytes: 0, download_total_bytes: 0, elapsed_seconds: null, failed: 0,
    },
    scored_count: 0,
    has_results: false,
    production_threshold: 58,
    ...overrides,
  };
}

function reportBody(overrides: Record<string, unknown> = {}) {
  return {
    verdict: {
      system_kappa: 0.019,
      target: 0.61,
      meets_target: false,
      human_ceiling_kappa: 0.494,
      attainable_max_low: 0.602,
      attainable_max_high: 0.742,
      level: "below_target",
      summary:
        "The system agrees with an individual teacher at kappa 0.019, short of the 0.61 target by 0.591.",
    },
    per_rater_agreement: {
      n: 9308,
      rater_count: 3,
      mean_cohen_kappa: 0.019,
      target: 0.61,
      meets_target: false,
      per_rater: [
        { rater: 1, cohen_kappa: 0.0194, accuracy: 0.559 },
        { rater: 2, cohen_kappa: 0.0158, accuracy: 0.562 },
        { rater: 3, cohen_kappa: 0.0207, accuracy: 0.560 },
      ],
    },
    oracle_bound: { contaminated: 0.742, uncontaminated: 0.602, dropped_for_ties: 1266 },
    benchmark_protocol: {
      threshold: 58, production_threshold: 58, recording_count: 1850,
      speaker_count: 49, rated_word_count: 9400,
      citation: "OMPAL corpus … CC BY 4.0.",
      population_caveat: "OMPAL speakers are French-L1 learners reading prompted sentences.",
      threshold_warning: "shipping a threshold picked here would be test-set leakage.",
    },
    pass_fail_agreement: { n: 9400, accuracy: 0.88, f1: 0.91, cohen_kappa: 0.58 },
    by_expected_tone: {
      "1": { n: 2000, accuracy: 0.9, f1: 0.92, cohen_kappa: 0.6 },
      "2": { n: 2400, accuracy: 0.85, f1: 0.88, cohen_kappa: 0.55 },
      "3": { n: 2500, accuracy: 0.82, f1: 0.85, cohen_kappa: 0.5 },
      "4": { n: 2500, accuracy: 0.91, f1: 0.93, cohen_kappa: 0.63 },
    },
    by_population: {
      learners: { n: 9000, accuracy: 0.87, cohen_kappa: 0.57 },
      natives: { n: 400, accuracy: 0.97, cohen_kappa: 0.4 },
    },
    human_ceiling: {
      rater_count: 3, item_count: 9000, mean_pairwise_cohen_kappa: 0.62,
      fleiss_kappa: 0.61, unanimous_item_count: 7800, unanimous_rate: 0.867,
    },
    score_agreement: {
      accuracy: { n: 1850, spearman_correlation: 0.71 },
      fluency: { n: 1850, spearman_correlation: 0.64 },
      mean_absolute_error: null,
      note: "Not applicable: OMPAL rates utterances on a 1-5 rubric…",
    },
    exclusions: { neutral_tone: 820, alignment_mismatch: 12, unjudged_by_analyzer: 3558 },
    release_gate: {
      checks: [
        { name: "accuracy", passed: true, actual: 0.88, operator: ">=", threshold: 0.85, applicable: true, detail: "" },
        { name: "mean_absolute_error", passed: false, actual: null, operator: "<=", threshold: 12, applicable: false, detail: "Not applicable: OMPAL rates…" },
      ],
      applicable_passed: true,
      complete: false,
      note: "Incomplete: this corpus cannot supply an absolute-scale score error.",
    },
    audit: {
      disagreement_count: 2,
      disagreements: [
        { utterance_id: "00200101", speaker_id: "SPEAKER02001", word: "很", expected_tone: 3, system_passed: false, teacher_passed: true, rater_labels: [true, true, false] },
      ],
      truncated: false,
    },
    ...overrides,
  };
}

function mockFetch(handlers: { status?: unknown; report?: unknown; runStatus?: number }) {
  return vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url);
    if (href.includes("/status")) {
      return new Response(JSON.stringify(handlers.status ?? statusBody()), { status: 200 });
    }
    if (href.includes("/report")) {
      if (!handlers.report) return new Response("{}", { status: 404 });
      return new Response(JSON.stringify(handlers.report), { status: 200 });
    }
    if (href.includes("/run") && init?.method === "POST") {
      return new Response(JSON.stringify({ started: true }), {
        status: handlers.runStatus ?? 200,
      });
    }
    return new Response("{}", { status: 200 });
  });
}

describe("TeacherBenchmarkPage", () => {
  it("offers to download the corpus when it is not present", async () => {
    vi.stubGlobal("fetch", mockFetch({}));
    render(<TeacherBenchmarkPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Download corpus/ })).toBeInTheDocument(),
    );
    expect(screen.getByText(/CC BY 4.0/)).toBeInTheDocument();
  });

  it("shows scoring progress while a run is in flight", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "OMPAL … CC BY 4.0." },
        job: {
          phase: "scoring", running: true, done: 847, total: 1850,
          message: "Scoring 1850 utterances…", error: null,
          downloaded_bytes: 0, download_total_bytes: 0, elapsed_seconds: 92, failed: 3,
        },
      }),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText(/847 \/ 1850/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByText(/3 unscorable/)).toBeInTheDocument();
  });

  it("leads with the verdict against the committed target", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "OMPAL … CC BY 4.0." },
        has_results: true,
        scored_count: 1850,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() =>
      expect(screen.getByText(/short of the 0.61 target/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Our system vs one teacher")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("Teachers vs each other")).toBeInTheDocument();
    // The attainable maximum must stay visible so the target is always read
    // against what a perfect system could actually reach.
    expect(screen.getByText("Best a perfect system could do")).toBeInTheDocument();
    expect(screen.getByText(/0.60.*0.74/)).toBeInTheDocument();
  });

  it("shows the per-rater spread behind the averaged headline", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "c" },
        has_results: true,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText(/rater 1/)).toBeInTheDocument());
    expect(screen.getByText(/rater 3/)).toBeInTheDocument();
  });

  it("labels raw agreement as gameable so it is not read as success", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "c" },
        has_results: true,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText(/Gameable/)).toBeInTheDocument());
  });

  it("breaks agreement down per tone so a weak tone cannot hide", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "c" },
        has_results: true,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText("Tone 3")).toBeInTheDocument());
    expect(screen.getByText("82.0%")).toBeInTheDocument();
  });

  it("marks the non-applicable release-gate criterion instead of showing it as a failure", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "c" },
        has_results: true,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText("mean absolute error")).toBeInTheDocument());
    expect(screen.getByText("Not applicable")).toBeInTheDocument();
    expect(screen.getByText(/cannot supply an absolute-scale score error/)).toBeInTheDocument();
  });

  it("warns that moving the threshold must not drive a shipping decision", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "c" },
        has_results: true,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText(/test-set leakage/)).toBeInTheDocument());
    expect(screen.getByRole("slider", { name: "Pass threshold" })).toHaveValue("58");
  });

  it("surfaces the population caveat and what was excluded", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        corpus: { downloaded: true, wav_count: 1850, citation: "c" },
        has_results: true,
      }),
      report: reportBody(),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText(/French-L1 learners/)).toBeInTheDocument());
    expect(screen.getByText(/unjudged by analyzer \(3558\)/)).toBeInTheDocument();
  });

  it("reports a failed run instead of leaving the page blank", async () => {
    vi.stubGlobal("fetch", mockFetch({
      status: statusBody({
        job: {
          phase: "failed", running: false, done: 0, total: 0,
          message: "Benchmark run failed.", error: "Network unreachable",
          downloaded_bytes: 0, download_total_bytes: 0, elapsed_seconds: 4, failed: 0,
        },
      }),
    }));
    render(<TeacherBenchmarkPage />);
    await waitFor(() => expect(screen.getByText("Network unreachable")).toBeInTheDocument());
  });

  it("starts a run when the teacher asks for one", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch({});
    vi.stubGlobal("fetch", fetchMock);
    render(<TeacherBenchmarkPage />);
    await user.click(await screen.findByRole("button", { name: /Download corpus/ }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => String(url).includes("/run") && (init as RequestInit)?.method === "POST",
        ),
      ).toBe(true),
    );
  });
});
