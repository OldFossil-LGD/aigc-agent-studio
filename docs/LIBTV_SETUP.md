# Connect LibTV to your agent

AIGC Agent Studio's production workflow is built around LibTV. The agent handles the brief and creative decisions, this skill supplies the workflow and checks, and LibTV provides the canvas, assets and model execution.

Install both the skill and a working LibTV connection before starting canvas production. Reading references, reviewing scripts and compiling the offline prompt sample can be done before connecting.

## Choose a connection

| Your agent environment | Connection |
| --- | --- |
| Can read the skill files and supports remote HTTP MCP with OAuth | Connect LibTV through MCP and complete account authorization in the host. |
| Can read the skill files and execute shell commands | Install and sign in to the official LibTV CLI in that execution environment. |
| Uses the Python platform executors in this repository | Install and sign in to the CLI, including when the host also has MCP. Those executors invoke the local `libtv` executable. |

Check the connection capabilities of your host. Support for loading a skill and support for calling platform tools are separate requirements.

## MCP setup

1. Open the official LibTV connection page and follow the instructions for your agent host.
2. For hosts with a remote HTTP MCP connection form, use the LibTV server URL below and complete OAuth with your own LibTV account.
3. Reload the host's tools or start a new session if its setup instructions require it.
4. Have the agent list accessible canvases with the connected LibTV tools. Confirm that the intended account and canvas are accessible before requesting changes.

~~~text
https://mcp.liblib.tv/mcp
~~~

The official marketplace documents the remote HTTP endpoint and per-user authorization. Host-specific setup is available from LibTV. [Official connection page](https://www.liblib.tv/plugin) · [Official marketplace](https://github.com/liblib-ai/marketplace)

An MCP login authorizes the host's MCP connection. Complete the CLI login separately when using the bundled Python platform executors.

## CLI setup

Install the official CLI using the CLI instructions on LibTV's connection page. The official release-discovery endpoint returns the current version, platform-specific installer URLs and the matching CLI skill package. Use the URLs in its response. [Official connection page](https://www.liblib.tv/plugin) · [Official CLI release metadata](https://api2.liblib.art/api/www/landing-activities/getById?id=240)

In that JSON response, parse `data.linkUrl` as JSON. The installer URLs are in `install.PowerShell`, `install.CMD` and `install.shell`. The `skill` field points to the official CLI documentation package.

After installation, run these commands in the environment where the agent executes tools.

~~~bash
libtv --help
libtv login web --open
libtv project list --page-size 1
~~~

Complete the browser login with your own account. The final command reads the canvas list. An empty list can be valid for an account with no accessible canvases. An authentication error requires completing the login before proceeding.

The CLI may be installed on a different machine or inside a container used by the agent. The executable and login must be available in that environment. If your environment cannot open a browser, run `libtv login web` and follow its printed login instructions.

The bundled executors look for `LIBTV_BIN` first, then `libtv` on PATH, then the current user's `~/.libtv/libtv` or `~/.libtv/libtv.exe`. For a custom install, set `LIBTV_BIN` in the agent's environment before starting the Python process.

PowerShell can point to the official current-user installation with the following setting.

~~~powershell
$env:LIBTV_BIN = Join-Path $env:USERPROFILE '.libtv/libtv.exe'
~~~

On macOS or Linux, use the following setting.

~~~bash
export LIBTV_BIN="$HOME/.libtv/libtv"
~~~

For an existing canvas, use its UUID when selecting the target. The CLI calls a canvas a `project` and a containing workspace a `workspace`. Its current-directory binding affects subsequent commands. Read the current CLI help and the [environment and binding notes](../references/libtv-cli-env-binding.md) before changing a binding.

## Before production

Have the agent read [SKILL.md](../SKILL.md), confirm the requested deliverable and identify the target LibTV account and canvas. First check access by listing or reading existing data. Then review the production plan and authorize the intended changes.

Media generation needs explicit approval and may consume LibTV credits. Your agent/model service can have its own charges. Current model capabilities and generation settings must come from current LibTV tools.

## Offline demo and Beta coverage

The [offline demo](DEMO.md) tests local prompt compilation without a LibTV connection. Its result covers that local path.

This is a public Beta. The repository's automated checks cover offline behavior on Windows and Ubuntu. The connection instructions use official LibTV sources, and the CLI command forms were checked against local help. Authenticated production across individual agent hosts requires separate verification.
