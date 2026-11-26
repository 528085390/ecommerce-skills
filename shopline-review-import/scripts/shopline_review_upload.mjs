import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { basename, join, resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

let store = "peakoom.myshopline.com";
let productHosts = new Set(["peakoom.com", "www.peakoom.com", store]);
let listUrl = `https://${store}/sl/apps/comment/comment-list`;
let recordsUrl = `${listUrl}/record`;
let profile = join(homedir(), ".local/share/shopline-review-import");
const importEndpoint = "/api/gsv-comment/comment/import";
const progressEndpoint = "/api/gsv-comment/common/progress/comment/page";
const labels = {
  import: /^(导入评价|Import reviews)$/i,
  history: /^(导入\/导出记录|Import Export Records)$/i,
  upload: /上传文件|Upload file/i,
  submit: /^(上传并导入|Upload and import)$/i,
  overwrite: /覆盖重复评价|Covering Duplicate Review/i,
};

function findBatch(page, filename) {
  return page.getByRole("row").filter({
    has: page.getByText(filename, { exact: true }),
  });
}

async function openReviewApp(page) {
  if (page.url() !== listUrl) await page.goto(listUrl, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: labels.import }).waitFor({ timeout: 120_000 });
  if (new URL(page.url()).hostname !== store) throw new Error("当前登录的后台与目标店铺不符。");
}

export function selectExistingReviewPage(contexts) {
  return contexts.flatMap((context) => context.pages()).find((page) => {
    const url = new URL(page.url());
    return url.origin === `https://${store}` && url.pathname.startsWith("/sl/apps/comment/");
  });
}

async function waitForProfileLogin(context, timeoutMs = 5 * 60_000) {
  let closed = false;
  context.once("close", () => { closed = true; });
  const initial = context.pages()[0] ?? await context.newPage();
  await initial.goto(listUrl, { waitUntil: "domcontentloaded", timeout: 30_000 }).catch((error) => {
    if (!initial.isClosed() && error.name !== "TimeoutError") throw error;
  });

  const deadline = Date.now() + timeoutMs;
  const opened = new WeakSet();
  let lastLocation;
  while (!closed && Date.now() < deadline) {
    const pages = context.pages();
    for (const page of pages) {
      const url = new URL(page.url());
      if (url.origin !== `https://${store}`) continue;
      if (url.pathname === new URL(listUrl).pathname &&
          await page.getByRole("button", { name: labels.import }).isVisible().catch(() => false)) {
        return page;
      }
      if (opened.has(page)) continue;
      if (url.pathname.startsWith("/sl/apps/comment/") && url.pathname !== new URL(listUrl).pathname) {
        opened.add(page);
        await page.goto(listUrl, { waitUntil: "domcontentloaded", timeout: 15_000 }).catch((error) => {
          if (!page.isClosed() && error.name !== "TimeoutError") throw error;
        });
      } else if (url.pathname.startsWith("/admin")) {
        const entry = page.getByText("商品评价", { exact: true });
        if (await entry.count() === 1 && await entry.isVisible()) {
          opened.add(page);
          await entry.click({ timeout: 5000 }).catch((error) => {
            if (!page.isClosed() && error.name !== "TimeoutError") throw error;
          });
        }
      }
    }
    const location = pages.map((page) => new URL(page.url()).hostname || "空白页").join(", ");
    if (location !== lastLocation) {
      console.error(`等待 ${store} 商品评价后台登录。已打开：${location || "无"}。`);
      lastLocation = location;
    }
    await setTimeout(1000);
  }
  throw new Error(closed ? "登录窗口已关闭，文件尚未提交。" : "未等到商品评价后台登录，文件尚未提交。");
}

function localDebuggerUrl(value) {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "[::1]", "localhost"].includes(url.hostname) ||
      !url.port || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("--connect 仅接受 Chrome 已授权的本机调试地址，例如 http://127.0.0.1:9222。");
  }
  return url.origin;
}

async function chromeDebuggerEndpoint(value) {
  if (value !== "auto") return localDebuggerUrl(value);
  const activePortFile = join(homedir(), "Library/Application Support/Google/Chrome/DevToolsActivePort");
  let file;
  try {
    file = await readFile(activePortFile, "utf8");
  } catch (error) {
    if (!["ENOENT", "EACCES", "EPERM"].includes(error.code)) throw error;
    throw new Error(`Chrome 尚未提供本机调试连接。请在已经登录 ${store} 的桌面 Chrome 中开启远程调试。`);
  }
  const [port, endpoint] = file.trim().split(/\r?\n/);
  if (!/^\d{1,5}$/.test(port) || Number(port) < 1 || Number(port) > 65535 ||
      !/^\/devtools\/browser\/[\w-]+$/.test(endpoint ?? "")) {
    throw new Error("Chrome 的本机调试地址格式无效。");
  }
  return `ws://127.0.0.1:${port}${endpoint}`;
}

async function callReviewApi(page, path, payload) {
  const response = await page.evaluate(async ({ path, payload, host, importEndpoint }) => {
    if (location.hostname !== host) throw new Error("当前登录的后台与目标店铺不符。");
    const headers = { accept: "application/json, text/plain, */*" };
    let body;
    if (path === importEndpoint) {
      headers.a_osudb_csrf = localStorage.getItem("CSRFToken") || "";
      const { filename, bytes } = payload;
      const content = Uint8Array.from(atob(bytes), (character) => character.charCodeAt(0));
      body = new FormData();
      body.append("file", new Blob([content], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }), filename);
      body.append("needIdempotent", "false");
      body.append("templateType", "1");
    } else {
      headers["content-type"] = "application/json";
      body = JSON.stringify(payload);
    }
    const result = await fetch(path, {
      method: "POST", credentials: "same-origin", redirect: "error", headers, body,
      signal: AbortSignal.timeout(30_000),
    });
    const json = await result.json().catch(() => null);
    const success = result.ok && [true, "true", "success", "SUCCESS"].includes(json?.success);
    return {
      success, httpStatus: result.status,
      code: ["string", "number"].includes(typeof json?.code) ? json.code : undefined,
      data: path === importEndpoint ? undefined : json?.data,
    };
  }, { path, payload, host: store, importEndpoint });
  if (!response.success) {
    throw new Error(`SHOPLINE 接口未确认成功（HTTP ${response.httpStatus}，代码 ${response.code ?? "无"}）。`);
  }
  return response.data;
}

export async function importReviewsViaApi(page, { file, expected, checkOnly, reserve }) {
  const filename = basename(file);
  await openReviewApp(page);
  await page.goto(recordsUrl, { waitUntil: "domcontentloaded" });
  const readBatch = async () => {
    const progress = await callReviewApi(page, progressEndpoint, {
      pageNum: 1, pageSize: 10, execActionList: [1, 2, 4, 5],
    });
    const list = progress?.list === null && progress.total === 0 ? [] : progress?.list;
    if (!Array.isArray(list)) {
      const shape = progress && typeof progress === "object"
        ? Object.entries(progress).slice(0, 12).map(([key, value]) =>
            `${key}:${Array.isArray(value) ? "array" : typeof value}`).join(", ")
        : String(progress === null ? "null" : typeof progress);
      throw new Error(`导入进度接口未返回任务列表（${shape}）。`);
    }
    const matches = list.filter(({ execAction, execName }) =>
      Number(execAction) === 1 && (execName === filename || execName?.startsWith(filename + " - ")));
    if (matches.length > 1) throw new Error("后台存在多个同名任务，请核对导入记录。");
    return matches[0];
  };
  let batch = await readBatch();
  if (!batch && checkOnly) throw new Error("最近 10 项导入导出记录里没有该文件。");
  if (!batch) {
    const bytes = (await readFile(file)).toString("base64");
    await openReviewApp(page);
    await reserve();
    try {
      await callReviewApi(page, importEndpoint, { filename, bytes });
    } catch (error) {
      throw new Error(`上传回执未确认。请使用 --check-only 查询，避免重复提交。 ${error.message}`);
    }
    await page.goto(recordsUrl, { waitUntil: "domcontentloaded" });
    batch = await readBatch();
  }
  for (let attempt = 0; attempt <= 30; attempt++) {
    if ([3, 4, 5, 6].includes(Number(batch?.execStatus))) {
      return {
        file: filename, expected, status: Number(batch.execStatus) === 6 ? "completed" : "failed",
        success: Number(batch.succeedCount ?? 0), failure: Number(batch.failedCount ?? 0),
        recordsUrl,
      };
    }
    if (attempt === 30) break;
    await setTimeout(attempt === 0 ? 1000 : 4000);
    batch = await readBatch();
  }
  throw new Error("后台暂未给出最终结果，请用 --check-only 查询这批文件。");
}

async function readResult(page, filename, expected) {
  const batch = findBatch(page, filename);
  const matches = await batch.count();
  if (!matches) return null;
  if (matches !== 1) throw new Error("发现多个同名导入任务，请在后台核对。");
  const record = await batch.innerText();
  const totals = record.match(/(?:成功\s*\/\s*失败|Success\s*\/\s*Failure)\s*[:：]\s*(\d+)\s*\/\s*(\d+)/i);
  const completed = /执行完成|Execute completed/i.test(record);
  const failed = /执行失败|Execute failed/i.test(record);
  if (!completed && !failed) return null;
  return {
    file: filename,
    expected,
    status: completed ? "completed" : "failed",
    success: totals ? Number(totals[1]) : null,
    failure: totals ? Number(totals[2]) : null,
    recordsUrl,
  };
}

async function waitResult(page, filename, expected) {
  for (let attempt = 0; attempt < 30; attempt++) {
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByText(/^(执行项目|Execute project)$/i).waitFor();
    const result = await readResult(page, filename, expected);
    if (result) return result;
    await setTimeout(4000);
  }
  throw new Error("后台暂未给出最终结果，请在导入记录查询这批文件。");
}

export async function importReviews(page, { file, title, expected, checkOnly, reserve }) {
  const filename = basename(file);
  await openReviewApp(page);
  const importButton = page.getByRole("button", { name: labels.import });
  const historyButton = page.getByRole("button", { name: labels.history });
  await historyButton.click();
  await page.getByText(/^(执行项目|Execute project)$/i).waitFor();
  if (checkOnly || await findBatch(page, filename).count()) {
    return waitResult(page, filename, expected);
  }

  const row = page.getByRole("row").filter({ has: page.getByText(title, { exact: true }) });
  const openProductList = async () => {
    await page.goto(listUrl, { waitUntil: "domcontentloaded" });
    await importButton.waitFor();
    await row.waitFor({ timeout: 8_000 }).catch(async () => {
      const search = page.locator('input[placeholder]:visible');
      if (await search.count() !== 1) {
        throw new Error("未能唯一定位商品搜索框，请按商品名称筛选后核对目标商品。");
      }
      await search.fill(title);
      await search.press("Enter");
      await row.waitFor({ timeout: 10_000 });
    });
  };
  await openProductList();

  await importButton.click();
  const uploadButton = page.getByRole("button", { name: labels.upload });
  const overwrite = page.getByRole("checkbox", { name: labels.overwrite });
  if (await overwrite.isChecked()) await overwrite.uncheck();
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), uploadButton.click()]);
  await chooser.setFiles(file);
  await page.getByText(filename, { exact: true }).waitFor();
  const submit = page.getByRole("button", { name: labels.submit });
  await submit.click({ trial: true });
  await reserve();
  await submit.click();

  await page.getByText(/正在导入您的评价列表|importing your review/i).first()
    .waitFor({ timeout: 8_000 }).catch(() => {});
  await page.goto(recordsUrl, { waitUntil: "domcontentloaded" });
  return waitResult(page, filename, expected);
}

async function main() {
  const { values } = parseArgs({ options: {
    product: { type: "string" }, title: { type: "string" }, file: { type: "string" },
    store: { type: "string" }, "product-host": { type: "string" }, "expected-count": { type: "string" },
    browser: { type: "boolean" }, "check-only": { type: "boolean" },
    headless: { type: "boolean" }, connect: { type: "string" },
    probe: { type: "boolean" }, help: { type: "boolean" },
  } });
  if (values.help) {
    console.log("node shopline_review_upload.mjs --store 后台域名 --product-host 前台域名 --product 商品链接 --file 评价.xlsx [--expected-count 条数] [--check-only] [--headless]");
    console.log("默认通过后台接口提交。可选 --browser --title '后台商品完整标题' 使用页面上传。");
    console.log(`首次使用请在脚本打开的 Chrome 标签页登录，再访问 ${listUrl}`);
    console.log("用 --connect auto 连接已开启远程调试的桌面 Chrome，或传入明确的本机调试地址。");
    console.log("用 --probe --store 后台域名 --headless 只读检查登录和评价应用接口，不上传文件。");
    return;
  }
  if (values.probe && (values.product || values.file || values.browser || values["check-only"])) {
    throw new Error("--probe 只检查店铺登录和应用接口，不与上传参数混用。");
  }
  if (!values.probe && (!values.product || !values.file || (values.browser && !values.title))) {
    throw new Error("请提供 --product 和 --file。使用 --browser 时还须提供 --title。");
  }
  if (values.store) {
    if (!/^[a-z0-9][a-z0-9.-]*\.myshopline\.com$/i.test(values.store)) {
      throw new Error("--store 须为 SHOPLINE 后台域名，例如 example.myshopline.com。");
    }
    store = values.store.toLowerCase();
    listUrl = `https://${store}/sl/apps/comment/comment-list`;
    recordsUrl = `${listUrl}/record`;
    profile = store === "peakoom.myshopline.com"
      ? profile : join(homedir(), ".local/share/shopline-review-import", store);
  }
  if (values["product-host"]) {
    const host = values["product-host"].toLowerCase();
    if (!/^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$/i.test(host) || host.endsWith(".myshopline.com")) {
      throw new Error("--product-host 须为已核对的前台域名，不含协议和路径。");
    }
    productHosts = new Set([host, store]);
  } else if (store !== "peakoom.myshopline.com") {
    productHosts = new Set([store]);
  }
  let product, file, count, digest;
  if (!values.probe) {
    product = new URL(values.product);
    if (product.protocol !== "https:" || !productHosts.has(product.hostname)) {
      throw new Error(`商品链接必须属于已配置的店铺：${[...productHosts].join("、")}。`);
    }
    file = resolve(values.file);
    const validator = fileURLToPath(new URL("./shopline_reviews.py", import.meta.url));
    const expectedCount = values["expected-count"];
    ({ count } = JSON.parse(execFileSync("python3", [
      validator, file, "--verify-upload", "--product", product.href,
      ...(expectedCount === undefined ? [] : ["--expected-count", expectedCount]),
    ], { encoding: "utf8" })));
    digest = createHash("sha256").update(await readFile(file)).digest("hex");
  }
  const receiptFolder = join(profile, "import-receipts");
  const reserve = async () => {
    await mkdir(receiptFolder, { recursive: true });
    try {
      await writeFile(join(receiptFolder, digest), basename(file) + "\n", { flag: "wx" });
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      throw new Error("这份文件已尝试提交，请先查询导入记录，避免重复。");
    }
  };
  const runtime = process.env.SHOPLINE_NODE_RUNTIME ?? join(
    homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node",
  );
  const require = createRequire(import.meta.url);
  const localPlaywright = fileURLToPath(new URL("../node_modules/playwright", import.meta.url));
  const playwrightPath = existsSync(localPlaywright)
    ? localPlaywright : join(runtime, "node_modules/playwright");
  if (!existsSync(playwrightPath)) {
    throw new Error("未找到 Playwright。请在 Skill 目录运行 npm ci，或设置 SHOPLINE_NODE_RUNTIME。");
  }
  const { chromium } = require(playwrightPath);
  const endpoint = values.connect ? await chromeDebuggerEndpoint(values.connect) : null;
  const attached = endpoint ? await chromium.connectOverCDP(endpoint, {
    timeout: 45_000,
  }).catch(() => {
    throw new Error("未能连接桌面 Chrome。请确认 Chrome 正在运行，并允许其弹出的调试连接。");
  }) : null;
  const context = attached ? null : await chromium.launchPersistentContext(profile, {
    channel: "chrome", headless: values.headless ?? false, viewport: { width: 1440, height: 950 },
  });
  try {
    const page = attached
      ? selectExistingReviewPage(attached.contexts())
      : await waitForProfileLogin(context, values.probe && values.headless ? 30_000 : 5 * 60_000);
    if (!page) throw new Error(`已连接 Chrome，但该会话没有打开 ${store} 商品评价页。`);
    if (values.probe) {
      await openReviewApp(page);
      await page.goto(recordsUrl, { waitUntil: "domcontentloaded" });
      const progress = await callReviewApi(page, progressEndpoint, {
        pageNum: 1, pageSize: 1, execActionList: [1, 2, 4, 5],
      });
      if (!Array.isArray(progress?.list) && !(progress?.list === null && progress?.total === 0)) {
        throw new Error("评价应用接口未返回可识别的导入记录结构。");
      }
      console.log(JSON.stringify({ store, authenticated: true, reviewApp: true, progressApi: true }, null, 2));
      return;
    }
    const upload = values.browser ? importReviews : importReviewsViaApi;
    const result = await upload(page, {
      file, title: values.title, expected: count, checkOnly: values["check-only"], reserve,
    });
    console.log(JSON.stringify(result, null, 2));
    if (result.status !== "completed" || result.success !== count || result.failure !== 0) {
      process.exitCode = 2;
    }
  } finally {
    if (attached) await attached.close();
    else await context.close();
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
