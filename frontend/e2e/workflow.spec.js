import path from "node:path";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";


const here = path.dirname(fileURLToPath(import.meta.url));
const tableFixture = path.resolve(here, "../../data/planos_demo/mesa_demo_001.dxf");
const visualEvidence = path.resolve(here, "../../.runtime/browser-ci/workflow-success.png");

function observeBrowserFailures(page) {
  const failures = [];
  page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const value = message.text();
    if (/Failed to load resource: the server responded with a status of (404|409)/.test(value)) return;
    failures.push(`console.error: ${value}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 500 && !response.url().includes("/semantic-explorer/")) {
      failures.push(`http ${response.status()}: ${response.url()}`);
    }
  });
  return failures;
}

async function uploadTable(page) {
  await page.goto("/");
  await expect(page.locator("#service-status")).toHaveText("Servicio disponible");
  await page.locator('#upload-form select[name="input_kind"]').selectOption("mounted_orthographic_views");
  await page.locator('#upload-form select[name="mode"]').selectOption("geometry_only");
  await page.locator("#drawing-file").setInputFiles(tableFixture);
  await page.locator("#upload-form").getByRole("button", { name: "Abrir" }).click();
  await expect(page).toHaveURL(/\?run=run-[A-Za-z0-9._-]+/);
  await expect(page.locator("#parts-body tr[data-component-id]")).toHaveCount(2);
  await expect(page.locator("#review-submit")).toBeEnabled();
}

test("storage denied at boot and persistence does not break the real upload workflow", async ({ page }) => {
  const failures = observeBrowserFailures(page);
  await page.addInitScript(() => {
    for (const method of ["getItem", "setItem", "removeItem"]) {
      Object.defineProperty(Storage.prototype, method, {
        configurable: true,
        value() {
          throw new DOMException("Storage access is denied", "SecurityError");
        },
      });
    }
  });

  await uploadTable(page);
  await page.reload();
  await expect(page.locator("#parts-body tr[data-component-id]")).toHaveCount(2);
  expect(failures).toEqual([]);
});

test("a throwing localStorage getter still allows URL-backed run recovery", async ({ page }) => {
  const failures = observeBrowserFailures(page);
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("Storage getter is denied", "SecurityError");
      },
    });
  });

  await uploadTable(page);
  await page.reload();
  await expect(page.locator("#revision-label")).toContainText("Revisión 1");
  expect(failures).toEqual([]);
});

test("disabled semantic explorer is explained without a dead navigation", async ({ page }) => {
  const failures = observeBrowserFailures(page);
  await page.goto("/");

  const link = page.locator("#semantic-explorer-link");
  const guidance = page.locator("#semantic-explorer-guidance");
  await expect(link).toBeHidden();
  await expect(guidance).not.toHaveAttribute("hidden", "");
  await expect(guidance).toContainText(/habilite|disponible|deshabilitado/i);
  expect(failures).toEqual([]);
});

test("a queued durable job exposes its position and can be cancelled", async ({ page }) => {
  const failures = observeBrowserFailures(page);
  let cancelled = false;

  await page.route(/\/api\/v1\/jobs(?:\/job-e2e-cancel(?:\/cancel)?)?$/, async (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.url().endsWith("/jobs")) {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ data: { id: "job-e2e-cancel", state: "queued", queue_position: 2, can_cancel: true } }),
      });
      return;
    }
    if (request.method() === "POST" && request.url().endsWith("/cancel")) {
      cancelled = true;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ data: { id: "job-e2e-cancel", state: "cancelled", cancel_requested: true, can_cancel: false } }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: cancelled
        ? { id: "job-e2e-cancel", state: "cancelled", cancel_requested: true, can_cancel: false }
        : { id: "job-e2e-cancel", state: "queued", queue_position: 2, can_cancel: true } }),
    });
  });

  await page.goto("/");
  await page.locator('#upload-form select[name="input_kind"]').selectOption("mounted_orthographic_views");
  await page.locator("#drawing-file").setInputFiles(tableFixture);
  await page.locator("#upload-form").getByRole("button", { name: "Abrir" }).click();
  await expect(page.locator("#job-status")).toContainText("posición 2");
  await expect(page.locator("#job-cancel")).toBeEnabled();
  await page.locator("#job-cancel").click();
  await expect(page.locator("#job-status")).toContainText("cancelado");
  expect(cancelled).toBe(true);
  expect(failures).toEqual([]);
});

test("recent execution restores a saved run without creating another job", async ({ page }) => {
  const failures = observeBrowserFailures(page);
  let createdJobs = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/v1\/jobs$/.test(request.url())) createdJobs += 1;
  });

  await uploadTable(page);
  const runUrl = page.url();
  expect(createdJobs).toBe(1);

  await page.locator('[data-panel="projects"]').click();
  const recent = page.locator("#recent-executions .recent-card").first();
  await expect(recent).toContainText("mesa_demo_001.dxf");
  await expect(recent).toContainText("Terminada");
  await recent.getByRole("link", { name: "Abrir resultado guardado" }).click();
  await expect(page).toHaveURL(runUrl);
  await expect(page.locator("#revision-label")).toContainText("Revisión 1");
  expect(createdJobs).toBe(1);
  expect(failures).toEqual([]);
});

test("upload result review and unsaved-change guard preserve the exact run", async ({ page }, testInfo) => {
  const failures = observeBrowserFailures(page);
  await uploadTable(page);
  const runUrl = page.url();
  await page.locator('[data-panel="review"]').click();

  const form = page.locator("#review-form");
  const scenario = form.locator('input[type="radio"]').first();
  if (await scenario.count()) await scenario.check();
  await form.locator("#reviewer-name").fill("QA navegador");
  await form.locator("#review-reason").fill("Comprobación reproducible del recorrido completo.");
  await expect(form).toHaveAttribute("data-dirty", "true");

  const switchDialogPromise = page.waitForEvent("dialog");
  const switchClickPromise = page.locator("#upload-form").getByRole("button", { name: "Abrir" }).click({ noWaitAfter: true });
  const switchDialog = await switchDialogPromise;
  expect(switchDialog.type()).toBe("confirm");
  await switchDialog.dismiss();
  await switchClickPromise;
  await expect(page.locator("#review-reason")).toHaveValue("Comprobación reproducible del recorrido completo.");
  await expect(page).toHaveURL(runUrl);

  const dialogPromise = page.waitForEvent("dialog");
  const reloadPromise = page.reload({ waitUntil: "domcontentloaded" });
  const dialog = await dialogPromise;
  expect(dialog.type()).toBe("beforeunload");
  await dialog.accept();
  await reloadPromise;
  await expect(page).toHaveURL(runUrl);
  await expect(page.locator("#revision-label")).toContainText("Revisión 1");

  await page.locator('[data-panel="review"]').click();
  if (await scenario.count()) await scenario.check();
  await form.locator("#reviewer-name").fill("QA navegador");
  await form.locator("#review-reason").fill("Comprobación reproducible del recorrido completo.");

  await form.locator("#review-submit").click();
  await expect(page.locator("#review-message")).toContainText("Decisión registrada");
  await expect(form).toHaveAttribute("data-dirty", "false");
  await expect(page.locator("#revision-label")).toContainText("Revisión 2");

  await page.reload();
  await expect(page).toHaveURL(runUrl);
  await expect(page.locator("#revision-label")).toContainText("Revisión 2");
  mkdirSync(path.dirname(visualEvidence), { recursive: true });
  await page.locator("main").screenshot({ path: visualEvidence });
  await testInfo.attach("reviewed-workflow", {
    path: visualEvidence,
    contentType: "image/png",
  });
  expect(failures).toEqual([]);
});
