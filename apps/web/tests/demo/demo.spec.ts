import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The demo tour (`make demo`): signs in to a library seeded with part of the evaluation corpus,
 * uploads one more document, searches across languages, asks with citations, is refused when
 * the documents do not know, and browses the knowledge graph. Records a video and writes the
 * README screenshots to docs/images.
 */

const REPOSITORY = path.resolve(__dirname, "../../../..");
const CORPUS = path.join(REPOSITORY, "eval/corpus");
const IMAGES = path.join(REPOSITORY, "docs/images");
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3100";

/** Uploaded before the tour starts, so the library looks lived in. */
const SEEDED = [
  "api-rate-limits.md",
  "api-rate-limits-partner.md",
  "billing-error-codes.md",
  "incident-postmortem-err-4711.md",
  "data-retention-policy.md",
  "employee-handbook.md",
  "kebijakan-cuti.md",
  "buku-panduan-gudang.md",
  "status-pengiriman.md",
  "master-services-agreement.pdf",
  "field-study-cover-crops.pdf",
  "travel-expense-policy.md",
  "engineer-onboarding.md",
  "release-notes.md",
];
/** Uploaded during the tour, through the Library page. */
const UPLOADED = "incident-runbook.md";

const account = {
  email: "ada@example.com",
  // Throwaway: the demo stack's database lives in memory and is gone after the recording.
  password: `demo ${crypto.randomUUID()}`,
};

type DocumentPage = { items: Array<{ status: string }> };
type GraphOverview = { nodes: unknown[] };

async function waitFor(check: () => Promise<boolean>, what: string, seconds = 300) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    if (await check()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out waiting for ${what}`);
}

async function upload(api: APIRequestContext, file: string) {
  const response = await api.post("/api/v1/documents", {
    multipart: {
      file: {
        name: file,
        mimeType: file.endsWith(".pdf") ? "application/pdf" : "text/markdown",
        buffer: readFileSync(path.join(CORPUS, file)),
      },
    },
  });
  expect(response.status(), await response.text()).toBe(202);
}

test.beforeAll(async () => {
  const api = await request.newContext({
    baseURL: BASE_URL,
    // State-changing requests must come from the app's origin (CSRF protection).
    extraHTTPHeaders: { Origin: BASE_URL },
  });
  const registered = await api.post("/api/v1/auth/register", {
    data: {
      invite_code: process.env.E2E_INVITE_CODE,
      display_name: "Ada",
      email: account.email,
      password: account.password,
    },
  });
  expect(registered.status(), await registered.text()).toBe(201);
  for (const file of SEEDED) {
    await upload(api, file);
  }
  await waitFor(async () => {
    const page = (await (await api.get("/api/v1/documents?limit=50")).json()) as DocumentPage;
    return page.items.length === SEEDED.length && page.items.every((d) => d.status === "ready");
  }, "the seeded documents to be processed");
  await waitFor(async () => {
    const graph = (await (await api.get("/api/v1/graph")).json()) as GraphOverview;
    return graph.nodes.length >= 20;
  }, "the knowledge graph");
  // The first search loads the embedding model into the API; do it before recording.
  await api.post("/api/v1/retrieval/search", { data: { query: "warm up", top_k: 1 } });
  await api.dispose();
});

/** A caption at the bottom of the video. CSSOM styles are allowed by the page's CSP. */
async function caption(page: Page, text: string) {
  await page.evaluate((value) => {
    let box = document.getElementById("demo-caption");
    if (!box) {
      box = document.createElement("div");
      box.id = "demo-caption";
      Object.assign(box.style, {
        position: "fixed",
        left: "50%",
        bottom: "24px",
        transform: "translateX(-50%)",
        maxWidth: "880px",
        padding: "10px 18px",
        borderRadius: "10px",
        background: "rgba(15, 23, 42, 0.88)",
        color: "white",
        font: "500 16px/1.4 system-ui, sans-serif",
        textAlign: "center",
        zIndex: "2147483647",
        pointerEvents: "none",
      });
      document.body.appendChild(box);
    }
    box.textContent = value;
    box.style.display = "block";
  }, text);
}

/** A screenshot for the README, without the caption. */
async function shot(page: Page, name: string) {
  await page.evaluate(() => {
    const box = document.getElementById("demo-caption");
    if (box) {
      box.style.display = "none";
    }
  });
  await page.mouse.move(0, 0);
  await page.screenshot({ path: path.join(IMAGES, `${name}.png`) });
  await page.evaluate(() => {
    const box = document.getElementById("demo-caption");
    if (box) {
      box.style.display = "block";
    }
  });
}

const pause = (page: Page, ms = 1800) => page.waitForTimeout(ms);

test("demo tour", async ({ page }) => {
  await test.step("sign in", async () => {
    await page.goto("/login");
    await caption(page, "KnowVault — your documents, searchable and answerable with citations");
    await pause(page);
    await page.getByLabel("Email").pressSequentially(account.email, { delay: 25 });
    await page.getByLabel("Password").fill(account.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await caption(page, "The dashboard: what is in the library and where to start");
    await pause(page);
    await shot(page, "dashboard");
  });

  await test.step("upload a document", async () => {
    await page.getByRole("link", { name: "Library" }).first().click();
    await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible();
    await caption(page, `The library: ${SEEDED.length} documents — Markdown and PDF, English and Indonesian`);
    await pause(page);
    await shot(page, "library");
    await caption(page, "Uploading a runbook: the worker extracts, chunks and embeds it");
    await page.getByLabel("Choose a file to upload").setInputFiles(path.join(CORPUS, UPLOADED));
    const uploaded = page.getByRole("link", { name: /incident.runbook/i }).first();
    await expect(uploaded).toBeVisible();
    await pause(page, 2500);
    await uploaded.click();
    await expect(page).toHaveURL(/\/library\/[0-9a-f-]{36}$/);
    await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible();
    await caption(page, "Ready: every passage keeps its heading trail, so citations can point at it");
    await pause(page, 2500);
    await shot(page, "document");
  });

  await test.step("search across languages", async () => {
    await page.getByRole("link", { name: "Search" }).first().click();
    await caption(page, "Search by meaning: an Indonesian question finds the English policy");
    await page
      .getByLabel("Search query")
      .pressSequentially("Berapa lama permintaan penghapusan data pribadi harus diselesaikan?", {
        delay: 30,
      });
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Search results" })).toBeVisible();
    await pause(page, 3000);
    await shot(page, "search");
  });

  await test.step("ask with citations", async () => {
    await page.getByRole("link", { name: "Ask" }).first().click();
    await caption(page, "Ask: answers come only from your documents, with numbered citations");
    await page
      .getByLabel("Your question")
      .pressSequentially("What should I do when an import fails with ERR_4711?", { delay: 30 });
    await page.keyboard.press("Enter");
    const answer = page.getByRole("article", { name: "Answer" }).last();
    await expect(answer).toHaveAttribute("aria-busy", "false");
    await pause(page);
    await answer.getByRole("button", { name: "Show source 1" }).click();
    await caption(page, "Every [n] opens the exact passage it came from");
    await pause(page, 2500);
    await shot(page, "answer");

    await caption(page, "No evidence, no answer: questions outside the documents are refused");
    await page
      .getByLabel("Your question")
      .pressSequentially("Who won the football World Cup in 2022?", { delay: 30 });
    await page.keyboard.press("Enter");
    await expect(page.getByText("Not in your documents").last()).toBeVisible();
    await pause(page, 2500);
  });

  await test.step("browse the knowledge graph", async () => {
    await page.getByRole("link", { name: "Graph" }).first().click();
    await caption(page, "The knowledge graph: names and codes, linked when they share a passage");
    const node = page.getByRole("link", { name: /^ERR_4711, code/ });
    await expect(node).toBeVisible();
    await pause(page);
    await shot(page, "graph");
    await node.hover();
    await caption(page, "Hovering an entity highlights what it is mentioned with");
    await pause(page, 2500);
    await node.click();
    await expect(page.getByRole("heading", { name: "ERR_4711" })).toBeVisible();
    await caption(page, "An entity: every passage that mentions it, its other spellings and relations");
    await pause(page, 2500);
    await shot(page, "entity");
    await page.getByRole("link", { name: /^Open passage/ }).first().click();
    await expect(page).toHaveURL(/#chunk-\d+$/);
    await caption(page, "…and straight back to the passage in its document");
    await pause(page, 3000);
  });
});
