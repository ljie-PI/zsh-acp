# zsh-acp Zsh Plugin

`zsh-acp` Zsh plugin integrates any ACP-compatible agent (Kimi, Claude, Codex, Gemini, Copilot, OpenCode, Qwen, etc.) into Zsh.

Press `Ctrl-X`, type your request, and the plugin routes it through a built-in ACP client to your chosen agent with a persistent `zsh-session`.

## Usage

- Press `Ctrl-X` in Zsh to start talking to your ACP agent.
- Press `Ctrl-X` again to exit ACP agent mode.

## Requirements

- Zsh 5.4+
- `python3` (for the built-in ACP client)
- `kimi` binary available in `$PATH` (fallback when Python is unavailable)

## Configuration

Control the plugin via environment variables in your `.zshrc`:

```zsh
# Use any ACP-compatible agent: claude, codex, gemini, copilot, opencode, kimi, etc.
export ZSH_ACP_AGENT="kimi"

# Fix the session name so all agent interactions share one persistent session
export ZSH_ACP_SESSION="zsh-session"

# Permission policy: approve_reads (default) | approve_all | deny_all
export ZSH_ACP_PERMISSIONS="approve_reads"
```

### How it works

| Setup | What happens |
|-------|--------------|
| `python3` available | Built-in `acp_client.py` speaks ACP to any configured agent, reusing `zsh-session` |
| `python3` missing | Falls back to native `kimi --session <session> -c "<cmd>"` |

### Adding custom agents

Edit `~/.config/zsh-acp/config.json`:

```json
{
  "agents": {
    "my-agent": {
      "command": "/path/to/agent",
      "args": ["--acp"],
      "env": {}
    }
  }
}
```

## Installation

Pick the method that matches your Zsh setup.

### Manual (`.zshrc`)

```zsh
# clone anywhere you prefer
git clone https://github.com/MoonshotAI/zsh-zsh-acp.git ~/.zsh/zsh-acp

# load the plugin in .zshrc
source ~/.zsh/zsh-acp/zsh-acp.plugin.zsh
```

Open a new shell (or `exec zsh`) to activate the handler.

> **Tip:** On first use (when you press `Ctrl-X` and type a command), the plugin will prompt you to pick a default agent from the built-in presets. You can always change it later by editing `~/.config/zsh-acp/config.json` or setting `ZSH_ACP_AGENT`.

### Oh My Zsh

```zsh
git clone https://github.com/MoonshotAI/zsh-zsh-acp.git \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-acp

# in ~/.zshrc
plugins=(... zsh-acp)
```

Reload Zsh to pick up the plugin.

### Antigen

```zsh
antigen bundle MoonshotAI/zsh-zsh-acp
antigen apply
```

### Zinit

```zsh
zinit light MoonshotAI/zsh-zsh-acp
```

### Znap

```zsh
znap source MoonshotAI/zsh-zsh-acp
```

### Fig

```zsh
fig plugin install MoonshotAI/zsh-zsh-acp
```

### Zplug

```zsh
zplug "MoonshotAI/zsh-zsh-acp", as:plugin
```
