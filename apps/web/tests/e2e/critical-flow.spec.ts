import { expect, test } from "@playwright/test";

/**
 * The critical path of docs/ARCHITECTURE.md §14: register → add a document → wait until it is
 * ready → search → ask → open the citation. Runs against the fake models, so answers quote the
 * matching sentence instead of being written by a language model.
 */
test("register, add a note, search, ask, open the citation and delete the account", async ({
  page,
}) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "e2e correct horse battery";

  await test.step("register with an invite", async () => {
    await page.goto("/register");
    await page.getByLabel("Invite code").fill(process.env.E2E_INVITE_CODE ?? "");
    await page.getByLabel("Name").fill("E2E");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  let documentPath = "";
  await test.step("write a note and wait until it is processed", async () => {
    await page.goto("/library/notes/new");
    await page.getByLabel("Title").fill("Leave policy");
    await page
      .getByLabel("Content (Markdown)")
      .fill(
        "# Annual leave\n\nEmployees get twelve days of annual leave per year. " +
          "Unused days expire at the end of March.",
      );
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page).toHaveURL(/\/library\/[0-9a-f-]{36}$/);
    documentPath = new URL(page.url()).pathname;
    await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible({
      timeout: 60_000,
    });
  });

  await test.step("find it by searching", async () => {
    await page.goto("/search?q=annual%20leave%20days");
    await expect(page.getByRole("link", { name: "Leave policy" }).first()).toBeVisible();
  });

  await test.step("ask, read the cited passage and open it in the document", async () => {
    await page.getByRole("link", { name: "Ask" }).first().click();
    await page.getByLabel("Your question").fill("How many days of annual leave do employees get?");
    await page.keyboard.press("Enter");

    const answer = page.getByRole("article", { name: "Answer" });
    await expect(answer).toContainText("twelve days of annual leave");
    await answer.getByRole("button", { name: "Show source 1" }).click();
    const sources = answer.getByRole("list", { name: "Sources" });
    await expect(sources.locator("blockquote")).toContainText("Unused days expire");

    await sources.getByRole("link", { name: "Leave policy" }).click();
    await expect(page).toHaveURL(new RegExp(`${documentPath}#chunk-0$`));
  });

  await test.step("a question the documents cannot answer is refused", async () => {
    await page.goto("/chat");
    await page.getByLabel("Your question").fill("Who won the football match yesterday?");
    await page.keyboard.press("Enter");
    await expect(page.getByText("Not in your documents")).toBeVisible();
  });

  await test.step("delete the account", async () => {
    await page.goto("/account");
    await page.getByLabel("Current password").fill(password);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Delete my account" }).click();
    await expect(page).toHaveURL(/\/login\?deleted=1$/);
    await expect(page.getByText("Your account and all its data were deleted.")).toBeVisible();
  });
});
