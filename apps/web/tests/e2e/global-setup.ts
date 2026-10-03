import { execSync } from "node:child_process";
import path from "node:path";

const REPOSITORY = path.resolve(__dirname, "../../../..");
const DEFAULT_COMMAND =
  "docker compose -f compose.e2e.yaml exec -T api knowvault create-invite --days 1";

/** Creates an invite code for the tests, unless E2E_INVITE_CODE is already set. */
export default function globalSetup(): void {
  if (process.env.E2E_INVITE_CODE) {
    return;
  }
  const output = execSync(process.env.E2E_INVITE_COMMAND ?? DEFAULT_COMMAND, {
    cwd: REPOSITORY,
    encoding: "utf8",
  });
  const code = output.match(/:\s*(\S+)\s*$/m)?.[1];
  if (!code) {
    throw new Error(`No invite code in the output of the invite command:\n${output}`);
  }
  // Workers inherit the environment of the process that ran global setup.
  process.env.E2E_INVITE_CODE = code;
}
