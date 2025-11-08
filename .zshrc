# Environment variables
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - zsh)"

eval "$(fnm env --use-on-cd --shell zsh)"
eval "$(rbenv init -)"
test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh" || true

export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/emulator
export PATH=$PATH:$ANDROID_HOME/platform-tools
export JAVA_HOME=$HOME/Library/Java/JavaVirtualMachines/azul-17.0.13/Contents/Home
export BIOME_CONFIG_PATH=~/.config/biome.json

# zsh-syntax-highlighting
typeset -A ZSH_HIGHLIGHT_STYLES
ZSH_HIGHLIGHT_STYLES[path]='none'

if type brew &>/dev/null; then
  FPATH=$(brew --prefix)/share/zsh-completions:$FPATH
  autoload -Uz compinit
  compinit
fi
source /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

# Prompt (with git support)
autoload -U colors && colors
autoload -Uz vcs_info
ICON_BRANCH=$'\uE0A0'
zstyle ':vcs_info:*' enable git
zstyle ':vcs_info:git*' formats " %{$fg[red]%}($ICON_BRANCH:%b)"
precmd() {
  vcs_info
}
setopt PROMPT_SUBST
prompt=$'
(%D %*) <%?> [%~]${vcs_info_msg_0_}
%{$fg[cyan]%}%m %#%{$fg[default]%} '

# Aliases and utilities
export CLICOLOR=1
alias ll='ls -l'
alias la='ls -la'
alias bb='yarn'

function reset-icon-cache() {
  sudo rm -rfv /Library/Caches/com.apple.iconservices.store
  sudo rm /var/folders/*/*/*/com.apple.dock.iconcache;
  killall Dock
  killall Finder
}
