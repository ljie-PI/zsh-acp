# Fallback to ACP agent when a command is not found.

# Configure the prefix that marks commands for ACP fallback.
typeset -g __ZSH_ACP_PREFIX_CHAR
: "${__ZSH_ACP_PREFIX_CHAR:="✨"}"

typeset -g __ZSH_ACP_PREFIX
: "${__ZSH_ACP_PREFIX:="${__ZSH_ACP_PREFIX_CHAR} "}"

typeset -g __ZSH_ACP_PREFIX_ACTIVE=0
typeset -g __ZSH_ACP_WIDGETS_INSTALLED=0
typeset -g __ZSH_ACP_HAS_PREV_LINE_INIT=0
typeset -g __ZSH_ACP_HAS_PREV_LINE_PRE_REDRAW=0
typeset -g __ZSH_ACP_HAS_PREV_LINE_FINISH=0
typeset -gA __ZSH_ACP_GUARD_WIDGET_ALIASES=()

# Agent configuration for ACP support.
# Set ZSH_ACP_AGENT to use a specific agent (e.g., claude, codex, gemini, copilot, opencode, kimi).
# Set ZSH_ACP_SESSION to fix the session name.
# Set ZSH_ACP_PERMISSIONS to control auto-approval: approve_reads | approve_all | deny_all.
typeset -g __ZSH_ACP_AGENT
: "${__ZSH_ACP_AGENT:=${ZSH_ACP_AGENT:-kimi}}"

typeset -g __ZSH_ACP_SESSION
: "${__ZSH_ACP_SESSION:=${ZSH_ACP_SESSION:-zsh-session}}"

typeset -g __ZSH_ACP_PERMISSIONS
: "${__ZSH_ACP_PERMISSIONS:=${ZSH_ACP_PERMISSIONS:-approve_reads}}"

# Resolve plugin directory for finding acp_client.py.
typeset -g __ZSH_ACP_PLUGIN_DIR
__ZSH_ACP_PLUGIN_DIR="${0:A:h}"

# Preserve any previously defined handler so we can delegate if needed.
if (( $+functions[command_not_found_handler] )); then
  functions[__zsh_acp_original_command_not_found_handler]=$functions[command_not_found_handler]
fi

command_not_found_handler() {
  emulate -L zsh

  local missing_command="$1"
  local -a cmd_with_args=("$@")

  shift
  local -a remaining_args=("$@")

  # Nothing to do without a command name.
  if [[ -z "$missing_command" ]]; then
    if (( $+functions[__zsh_acp_original_command_not_found_handler] )); then
      __zsh_acp_original_command_not_found_handler "${cmd_with_args[@]}"
      return $?
    fi
    return 127
  fi

  local prefix_char="${__ZSH_ACP_PREFIX_CHAR:-✨}"

  local handled=false
  local -a effective_cmd=()

  if [[ "$missing_command" == "$prefix_char" ]]; then
    handled=true
    effective_cmd=("${remaining_args[@]}")
  elif [[ "$missing_command" == ${prefix_char}* ]]; then
    handled=true
    local stripped="${missing_command#$prefix_char}"
    if [[ -n "$stripped" ]]; then
      effective_cmd=("$stripped" "${remaining_args[@]}")
    else
      effective_cmd=("${remaining_args[@]}")
    fi
  fi

  if [[ "$handled" != true ]]; then
    if (( $+functions[__zsh_acp_original_command_not_found_handler] )); then
      __zsh_acp_original_command_not_found_handler "${cmd_with_args[@]}"
      return $?
    fi
    print -u2 "zsh: command not found: ${missing_command}"
    return 127
  fi

  if (( ${#effective_cmd[@]} == 0 )); then
    print -u2 "zsh-acp: nothing to run after '${prefix_char}'."
    return 127
  fi

  local full_cmd_quoted
  full_cmd_quoted="$(printf '%q ' "${effective_cmd[@]}")"
  full_cmd_quoted="${full_cmd_quoted% }"

  local full_cmd_raw
  full_cmd_raw="${effective_cmd[*]}"

  # First-run: create config if missing.
  if [[ ! -f "$HOME/.config/zsh-acp/config.json" ]]; then
    if command -v python3 >/dev/null 2>&1 && [[ -f "$__ZSH_ACP_PLUGIN_DIR/acp_client.py" ]]; then
      python3 "$__ZSH_ACP_PLUGIN_DIR/acp_client.py" --init
    else
      print -u2 "zsh-acp: python3 is required for first-time setup."
      return 127
    fi
  fi

  # Prefer the built-in Python ACP client.
  if command -v python3 >/dev/null 2>&1 && [[ -f "$__ZSH_ACP_PLUGIN_DIR/acp_client.py" ]]; then
    python3 "$__ZSH_ACP_PLUGIN_DIR/acp_client.py" \
      --agent "$__ZSH_ACP_AGENT" \
      --session "$__ZSH_ACP_SESSION" \
      --cwd "$PWD" \
      --permissions "$__ZSH_ACP_PERMISSIONS" \
      "$full_cmd_raw"
    return $?
  fi

  # Fallback to native agent (kimi).
  if [[ "$__ZSH_ACP_AGENT" != "kimi" ]]; then
    print -u2 "zsh-acp: python3 is required to use agent '${__ZSH_ACP_AGENT}'."
    return 127
  fi

  if ! command -v kimi >/dev/null 2>&1; then
    if (( $+functions[__zsh_acp_original_command_not_found_handler] )); then
      __zsh_acp_original_command_not_found_handler "${cmd_with_args[@]}"
      return $?
    fi
    print -u2 "kimi: command not found; unable to handle '${effective_cmd[1]}'."
    return 127
  fi

  kimi --session "$__ZSH_ACP_SESSION" -c "$full_cmd_quoted"
  return $?
}

__zsh_acp_toggle_prefix() {
  emulate -L zsh

  local prefix="${__ZSH_ACP_PREFIX:-${__ZSH_ACP_PREFIX_CHAR} }"
  local prefix_len=${#prefix}

  if [[ "$BUFFER" == "$prefix"* ]]; then
    BUFFER="${BUFFER#$prefix}"
    if (( CURSOR > prefix_len )); then
      CURSOR=$(( CURSOR - prefix_len ))
    else
      CURSOR=0
    fi
    __ZSH_ACP_PREFIX_ACTIVE=0
  else
    BUFFER="${prefix}${BUFFER}"
    CURSOR=$(( CURSOR + prefix_len ))
    __ZSH_ACP_PREFIX_ACTIVE=1
  fi
}

__zsh_acp_line_init() {
  emulate -L zsh

  # Add prefix at the start of a new line if prefix mode is active
  if (( __ZSH_ACP_PREFIX_ACTIVE )); then
    local prefix="${__ZSH_ACP_PREFIX:-${__ZSH_ACP_PREFIX_CHAR} }"
    BUFFER="${prefix}"
    CURSOR=${#prefix}
  fi

  if (( __ZSH_ACP_HAS_PREV_LINE_INIT )); then
    zle __zsh_acp_prev_line_init
  fi
}

__zsh_acp_line_pre_redraw() {
  emulate -L zsh

  if (( __ZSH_ACP_PREFIX_ACTIVE )); then
    local prefix="${__ZSH_ACP_PREFIX:-${__ZSH_ACP_PREFIX_CHAR} }"
    local prefix_len=${#prefix}

    if (( CURSOR < prefix_len )); then
      CURSOR=$prefix_len
    fi

    local buffer_len=${#BUFFER}
    if (( CURSOR > buffer_len )); then
      CURSOR=$buffer_len
    fi
  fi

  if (( __ZSH_ACP_HAS_PREV_LINE_PRE_REDRAW )); then
    zle __zsh_acp_prev_line_pre_redraw
  fi
}

__zsh_acp_line_finish() {
  emulate -L zsh

  if (( __ZSH_ACP_HAS_PREV_LINE_FINISH )); then
    zle __zsh_acp_prev_line_finish
  fi
}

__zsh_acp_guard_backward_action() {
  emulate -L zsh

  if (( ! __ZSH_ACP_PREFIX_ACTIVE )); then
    __zsh_acp_call_guarded_original
    return
  fi

  local prefix="${__ZSH_ACP_PREFIX:-${__ZSH_ACP_PREFIX_CHAR} }"
  local prefix_len=${#prefix}

  if [[ "$BUFFER" == "$prefix"* ]] && (( CURSOR <= prefix_len )); then
    zle beep 2>/dev/null
    return
  fi

  __zsh_acp_call_guarded_original
}

__zsh_acp_call_guarded_original() {
  emulate -L zsh

  local alias="${__ZSH_ACP_GUARD_WIDGET_ALIASES[$WIDGET]-}"
  if [[ -n "$alias" ]]; then
    zle "$alias" 2>/dev/null
  else
    zle ".${WIDGET}" 2>/dev/null
  fi
}

__zsh_acp_register_guard_widget() {
  emulate -L zsh

  local widget="$1"
  local alias="__zsh_acp_prev_${widget//-/_}"

  if zle -A "$widget" "$alias" 2>/dev/null; then
    __ZSH_ACP_GUARD_WIDGET_ALIASES[$widget]="$alias"
  else
    __ZSH_ACP_GUARD_WIDGET_ALIASES[$widget]=""
  fi

  zle -N "$widget" __zsh_acp_guard_backward_action
}

if [[ -o interactive ]]; then
  zle -N __zsh_acp_toggle_prefix

  local -a __zsh_acp_keymaps=("emacs" "viins")
  local keymap
  for keymap in "${__zsh_acp_keymaps[@]}"; do
    bindkey -M "$keymap" '^X' __zsh_acp_toggle_prefix 2>/dev/null
  done
  unset keymap __zsh_acp_keymaps

  if (( ! __ZSH_ACP_WIDGETS_INSTALLED )); then
    if zle -A zle-line-init __zsh_acp_prev_line_init 2>/dev/null; then
      __ZSH_ACP_HAS_PREV_LINE_INIT=1
    fi
    zle -N zle-line-init __zsh_acp_line_init

    if zle -A zle-line-pre-redraw __zsh_acp_prev_line_pre_redraw 2>/dev/null; then
      __ZSH_ACP_HAS_PREV_LINE_PRE_REDRAW=1
    fi
    zle -N zle-line-pre-redraw __zsh_acp_line_pre_redraw

    if zle -A zle-line-finish __zsh_acp_prev_line_finish 2>/dev/null; then
      __ZSH_ACP_HAS_PREV_LINE_FINISH=1
    fi
    zle -N zle-line-finish __zsh_acp_line_finish
    __zsh_acp_register_guard_widget backward-delete-char
    __zsh_acp_register_guard_widget backward-kill-word
    __zsh_acp_register_guard_widget vi-backward-delete-char
    __zsh_acp_register_guard_widget vi-backward-kill-word

    __ZSH_ACP_WIDGETS_INSTALLED=1
  fi
fi
