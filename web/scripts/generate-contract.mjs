import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import openapiTS, { astToString } from "openapi-typescript";
const [input, expectedVersion] = process.argv.slice(2);
if (!input || !expectedVersion)
  throw new Error(
    "Usage: npm run contract:generate -- <published-openapi.json> <expected-info.version>",
  );
const bytes = await readFile(resolve(input), "utf8");
const document = JSON.parse(bytes);
if (document.info?.version !== expectedVersion)
  throw new Error(
    "Published OpenAPI version does not match the explicitly requested version.",
  );
const directory = new URL("../src/contract/", import.meta.url);
await mkdir(directory, { recursive: true });
const ast = await openapiTS(document);
await writeFile(new URL("generated.ts", directory), astToString(ast));
await writeFile(
  new URL("version.ts", directory),
  `export const CONTRACT_VERSION = ${JSON.stringify(expectedVersion)} as const;\n`,
);
console.log(
  "Generated pinned types. Implement and verify the API-to-display adapter before enabling real operations.",
);
