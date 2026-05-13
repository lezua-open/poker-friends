import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Copy, Play, Send, Smile, Users } from "lucide-react";
import "./styles.css";

const API = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "http://127.0.0.1:8000";
const WS = (import.meta.env.VITE_WS_BASE_URL as string | undefined) || "ws://127.0.0.1:8000";
const REACTIONS = [
  { emoji: "👍", label: "好牌" },
  { emoji: "😅", label: "尴尬" },
  { emoji: "😂", label: "笑死" },
  { emoji: "🤔", label: "思考" },
  { emoji: "🔥", label: "厉害" },
  { emoji: "😭", label: "裂开" },
  { emoji: "👀", label: "看看" },
  { emoji: "🫡", label: "跟了" },
  { emoji: "💣", label: "全下？" },
  { emoji: "🏆", label: "漂亮" },
];

type Player = {
  id: string;
  nickname: string;
  seat: number;
  stack: number;
  hand: string[];
  currentBet: number;
  contribution: number;
  folded: boolean;
  allIn: boolean;
  ready: boolean;
  connected: boolean;
  isYou: boolean;
};

type Action = {
  type: string;
  label: string;
  min?: number;
  max?: number;
};

type ShowdownEntry = {
  playerId: string;
  nickname: string;
  isWinner: boolean;
  amount: number;
  handName: string;
  bestCards: string[];
  reason: string;
};

type GameState = {
  code: string;
  phase: string;
  smallBlind: number;
  bigBlind: number;
  dealerSeat: number;
  actorSeat: number | null;
  actionDeadline: number | null;
  autoStartDeadline: number | null;
  community: string[];
  pot: number;
  currentBet: number;
  messages: string[];
  lastResult: string;
  showdownSummary: ShowdownEntry[];
  isHost: boolean;
  hostId: string | null;
  allReady: boolean;
  canStart: boolean;
  waitingPlayers: string[];
  readyCount: number;
  eligibleCount: number;
  players: Array<Player | null>;
  actions: Action[];
};

function App() {
  const initialRoom = new URLSearchParams(window.location.search).get("room") || "";
  const [nickname, setNickname] = useState(localStorage.getItem("pf_nickname") || "");
  const [roomCode, setRoomCode] = useState(initialRoom.toUpperCase());
  const [session, setSession] = useState(() => {
    const code = localStorage.getItem("pf_code");
    const playerId = localStorage.getItem("pf_player");
    return code && playerId ? { code, playerId } : null;
  });
  const [state, setState] = useState<GameState | null>(null);
  const [error, setError] = useState("");
  const [raiseAmount, setRaiseAmount] = useState(40);
  const [chatText, setChatText] = useState("");
  const [confirmedShowdown, setConfirmedShowdown] = useState("");
  const [logTab, setLogTab] = useState<"chat" | "system">("chat");
  const [now, setNow] = useState(Date.now() / 1000);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!session) return;
    const socket = new WebSocket(`${WS}/ws/${session.code}/${session.playerId}`);
    wsRef.current = socket;
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "state") {
        setState(payload.state);
        const raise = payload.state.actions.find((action: Action) => action.type === "raise");
        if (raise?.min) setRaiseAmount(raise.min);
      }
      if (payload.type === "error") setError(payload.message);
    };
    socket.onclose = () => setError("连接已断开，刷新页面可尝试重连");
    return () => socket.close();
  }, [session]);

  const me = useMemo(() => state?.players.find((player) => player?.isYou) || null, [state]);
  const raiseAction = state?.actions.find((action) => action.type === "raise");
  const inviteUrl = state ? `${window.location.origin}?room=${state.code}` : "";
  const winners = new Set((state?.showdownSummary || []).filter((entry) => entry.isWinner).map((entry) => entry.playerId));
  const summaries = new Map((state?.showdownSummary || []).map((entry) => [entry.playerId, entry]));
  const showdownKey = state ? `${state.code}-${state.lastResult}-${state.showdownSummary.map((entry) => `${entry.playerId}:${entry.amount}`).join(",")}` : "";
  const showShowdownDialog = state?.phase === "showdown" && state.showdownSummary.length > 0 && confirmedShowdown !== showdownKey;
  const actionCountdown = state?.actionDeadline ? Math.max(0, Math.ceil(state.actionDeadline - now)) : null;
  const autoStartCountdown = state?.autoStartDeadline ? Math.max(0, Math.ceil(state.autoStartDeadline - now)) : null;
  const chatMessages = state?.messages.filter((message) => message.startsWith("CHAT|") || message.startsWith("REACTION|")) || [];
  const systemMessages = state?.messages.filter((message) => !message.startsWith("CHAT|") && !message.startsWith("REACTION|")) || [];
  const reactions = new Map<string, { emoji: string; label: string }>();
  for (const message of state?.messages || []) {
    const reaction = parseReaction(message);
    if (reaction) reactions.set(reaction.playerId, { emoji: reaction.emoji, label: reaction.label });
  }

  async function enter(createRoom: boolean) {
    setError("");
    const cleanName = nickname.trim();
    if (!cleanName) {
      setError("先输入昵称");
      return;
    }
    if (!createRoom && !roomCode.trim()) {
      setError("先输入房间码");
      return;
    }
    localStorage.setItem("pf_nickname", cleanName);
    const url = createRoom ? `${API}/rooms` : `${API}/rooms/${roomCode.trim().toUpperCase()}/join`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname: cleanName }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setError(payload.detail || "进入房间失败");
      return;
    }
    localStorage.setItem("pf_code", payload.code);
    localStorage.setItem("pf_player", payload.playerId);
    setSession({ code: payload.code, playerId: payload.playerId });
  }

  function send(payload: object) {
    wsRef.current?.send(JSON.stringify(payload));
  }

  function leave() {
    localStorage.removeItem("pf_code");
    localStorage.removeItem("pf_player");
    wsRef.current?.close();
    setSession(null);
    setState(null);
  }

  function sendChat() {
    const text = chatText.trim();
    if (!text) return;
    send({ type: "chat", text });
    setChatText("");
  }

  if (!session || !state) {
    return (
      <main className="entry">
        <section className="entry-panel">
          <div className="brand">
            <span className="mark">扑克</span>
            <div>
              <h1>朋友德州</h1>
              <p>创建房间，邀请朋友一起玩</p>
            </div>
          </div>
          <label>
            你的昵称
            <input value={nickname} onChange={(event) => setNickname(event.target.value)} placeholder="例如：小明" />
          </label>
          <div className="entry-actions">
            <button onClick={() => enter(true)}>
              <Play size={18} />
              创建新房间
            </button>
          </div>
          <div className="join-row">
            <input value={roomCode} onChange={(event) => setRoomCode(event.target.value)} placeholder="输入房间码" />
            <button className="secondary" onClick={() => enter(false)}>
              加入房间
            </button>
          </div>
          {error && <p className="error">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      {showShowdownDialog && <ShowdownDialog summary={state.showdownSummary} onConfirm={() => setConfirmedShowdown(showdownKey)} />}
      <section className="table-area">
        <div className="table-topbar">
          <div>
            <strong>房间码 {state.code}</strong>
            <span>小盲/大盲 {state.smallBlind}/{state.bigBlind}</span>
            {state.isHost && <span>你是房主</span>}
            {(state.phase === "lobby" || state.phase === "showdown") && <span>准备 {state.readyCount}/{state.eligibleCount}</span>}
            {autoStartCountdown !== null && <span className="countdown-text">自动开局 {autoStartCountdown}s</span>}
            {actionCountdown !== null && <span className="countdown-text">行动倒计时 {actionCountdown}s</span>}
          </div>
          <button className="icon-button" onClick={() => navigator.clipboard.writeText(inviteUrl)} title="复制邀请链接">
            <Copy size={18} />
          </button>
        </div>

        <div className="poker-table">
          {state.players.map((player, seat) => (
            <Seat
              key={seat}
              seat={seat}
              player={player}
              active={state.actorSeat === seat}
              dealer={state.dealerSeat === seat}
              winner={!!player && winners.has(player.id)}
              summary={player ? summaries.get(player.id) : undefined}
              reaction={player ? reactions.get(player.id) : undefined}
            />
          ))}
          <div className="board">
            <div className="pot">底池 {state.pot}</div>
            <div className="community">{[0, 1, 2, 3, 4].map((index) => <Card key={index} value={state.community[index]} />)}</div>
            <div className="phase">{phaseLabel(state.phase)}</div>
          </div>
        </div>

        <div className="action-bar">
          <div className="hero-hand">
            <span>{me?.nickname || "我的手牌"}</span>
            <div>{me?.hand.map((card) => <Card key={card} value={card} large />)}</div>
          </div>
          <div className="controls">
            {state.phase === "lobby" || state.phase === "showdown" ? (
              <>
                <button onClick={() => send({ type: "ready", ready: !me?.ready })}>{me?.ready ? "取消准备" : "准备"}</button>
                <button disabled={!state.canStart} onClick={() => send({ type: "start" })}>
                  <Play size={18} />
                  {state.isHost ? "开始一局" : "等待房主开始"}
                </button>
                {state.waitingPlayers.length > 0 && <span className="waiting-text">等待：{state.waitingPlayers.join("、")}</span>}
              </>
            ) : (
              <>
                {raiseAction && (
                  <div className="raise-box">
                    <span>加注到</span>
                    <input
                      type="range"
                      min={raiseAction.min}
                      max={raiseAction.max}
                      value={Math.min(raiseAmount, raiseAction.max || raiseAmount)}
                      onChange={(event) => setRaiseAmount(Number(event.target.value))}
                    />
                    <input
                      type="number"
                      min={raiseAction.min}
                      max={raiseAction.max}
                      value={raiseAmount}
                      onChange={(event) => setRaiseAmount(Number(event.target.value))}
                    />
                  </div>
                )}
                {state.actions.map((action) => (
                  <button
                    key={action.type}
                    className={action.type === "fold" ? "danger" : ""}
                    onClick={() => send({ type: "action", action: action.type, amount: action.type === "raise" ? raiseAmount : undefined })}
                  >
                    {action.label}
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      </section>

      <aside className="side-panel">
        <div className="panel-header">
          <Users size={18} />
          <strong>玩家列表</strong>
          <button className="link-button" onClick={leave}>
            离开房间
          </button>
        </div>
        <div className="player-list">
          {state.players.filter(Boolean).map((player) => (
            <div key={player!.id} className="player-line">
              <span>
                {player!.nickname}
                {player!.id === state.hostId && <em>房主</em>}
              </span>
              <strong>{player!.ready ? "已准备" : `${player!.stack} 筹码`}</strong>
            </div>
          ))}
        </div>
        {state.lastResult && <div className="result">{state.lastResult}</div>}
        <div className="log-tabs">
          <button className={logTab === "chat" ? "selected" : ""} onClick={() => setLogTab("chat")}>聊天</button>
          <button className={logTab === "system" ? "selected" : ""} onClick={() => setLogTab("system")}>记录</button>
        </div>
        <div className="log">
          {(logTab === "chat" ? chatMessages : systemMessages).map((message, index) => (
            <LogMessage key={`${message}-${index}`} message={message} />
          ))}
        </div>
        <div className="chat">
          <div className="emoji-wrap">
            <button className="icon-button" onClick={() => setEmojiOpen((value) => !value)} title="发送表情">
              <Smile size={18} />
            </button>
            {emojiOpen && (
              <div className="emoji-panel">
                {REACTIONS.map((reaction) => (
                  <button
                    key={reaction.emoji}
                    onClick={() => {
                      send({ type: "reaction", emoji: reaction.emoji });
                      setEmojiOpen(false);
                      setLogTab("chat");
                    }}
                  >
                    <span>{reaction.emoji}</span>
                    {reaction.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <input value={chatText} onChange={(event) => setChatText(event.target.value)} onKeyDown={(event) => event.key === "Enter" && sendChat()} placeholder="输入聊天内容" />
          <button className="icon-button" onClick={sendChat} title="发送消息">
            <Send size={18} />
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </aside>
    </main>
  );
}

function Seat({
  seat,
  player,
  active,
  dealer,
  winner,
  summary,
  reaction,
}: {
  seat: number;
  player: Player | null;
  active: boolean;
  dealer: boolean;
  winner: boolean;
  summary?: ShowdownEntry;
  reaction?: { emoji: string; label: string };
}) {
  return (
    <div className={`seat seat-${seat} ${active ? "active" : ""} ${winner ? "winner" : ""} ${player?.folded ? "folded" : ""} ${!player ? "empty" : ""}`}>
      {player ? (
        <>
          <div className="seat-main">
            <div className="avatar">{player.nickname.slice(0, 1).toUpperCase()}</div>
            <div className="seat-info">
              <strong>{player.nickname}</strong>
              <span>{player.stack} 筹码</span>
            </div>
            <div className="mini-cards">{player.hand.map((card, index) => <Card key={`${card}-${index}`} value={card} small />)}</div>
          </div>
          <div className="seat-tags">
            {player.currentBet > 0 && <div className="bet">下注 {player.currentBet}</div>}
            {player.allIn && <div className="badge">全下</div>}
            {!player.connected && <div className="badge muted">离线</div>}
            {summary && <div className="badge hand-badge">{summary.handName}</div>}
          </div>
          {reaction && <div className="reaction-bubble">{reaction.emoji} {reaction.label}</div>}
          {dealer && <div className="dealer">庄</div>}
        </>
      ) : (
        <span className="empty-seat">空座位</span>
      )}
    </div>
  );
}

function Card({ value, small = false, large = false }: { value?: string; small?: boolean; large?: boolean }) {
  const hidden = !value || value === "BACK";
  const red = value?.endsWith("H") || value?.endsWith("D");
  const label = hidden ? "" : `${rank(value?.[0] || "")}${suit(value?.[1] || "")}`;
  return <div className={`card ${small ? "small" : ""} ${large ? "large" : ""} ${hidden ? "back" : ""} ${red ? "red" : ""}`}>{label}</div>;
}

function LogMessage({ message }: { message: string }) {
  if (message.startsWith("CHAT|")) {
    const [, nickname, ...contentParts] = message.split("|");
    return (
      <div className="chat-message">
        <span>{nickname}</span>
        <p>{contentParts.join("|")}</p>
      </div>
    );
  }
  const reaction = parseReaction(message);
  if (reaction) {
    return (
      <div className="reaction-message">
        <span>{reaction.nickname}</span>
        <p>{reaction.emoji} {reaction.label}</p>
      </div>
    );
  }
  return <p className="system-message">{message}</p>;
}

function parseReaction(message: string) {
  if (!message.startsWith("REACTION|")) return null;
  const [, playerId, nickname, emoji, label] = message.split("|");
  if (!playerId || !nickname || !emoji || !label) return null;
  return { playerId, nickname, emoji, label };
}

function ShowdownPanel({ summary }: { summary: ShowdownEntry[] }) {
  return (
    <div className="showdown-panel">
      <strong>摊牌结果</strong>
      {summary.map((entry) => (
        <div key={entry.playerId} className={`showdown-row ${entry.isWinner ? "win" : ""}`}>
          <div>
            <span>{entry.nickname}</span>
            <small>{entry.reason}</small>
          </div>
          <div className="showdown-cards">{entry.bestCards.map((card) => <Card key={`${entry.playerId}-${card}`} value={card} small />)}</div>
          {entry.isWinner && <b>赢得 {entry.amount}</b>}
        </div>
      ))}
    </div>
  );
}

function ShowdownDialog({ summary, onConfirm }: { summary: ShowdownEntry[]; onConfirm: () => void }) {
  const winners = summary.filter((entry) => entry.isWinner);
  return (
    <div className="showdown-overlay">
      <div className="showdown-dialog">
        <div className="showdown-dialog-header">
          <span>摊牌结果</span>
          <strong>{winners.map((entry) => entry.nickname).join("、")} 获胜</strong>
        </div>
        <div className="showdown-dialog-list">
          {summary.map((entry) => (
            <div key={entry.playerId} className={`showdown-dialog-row ${entry.isWinner ? "win" : ""}`}>
              <div className="showdown-dialog-title">
                <span>{entry.nickname}</span>
                <b>{entry.handName}</b>
              </div>
              <div className="showdown-dialog-cards">
                {entry.bestCards.length > 0 ? entry.bestCards.map((card) => <Card key={`${entry.playerId}-${card}`} value={card} />) : <span className="no-cards">未摊牌</span>}
              </div>
              <p>{entry.reason}</p>
              {entry.isWinner && <strong className="win-amount">赢得 {entry.amount}</strong>}
            </div>
          ))}
        </div>
        <button onClick={onConfirm}>确认</button>
      </div>
    </div>
  );
}

function rank(value: string) {
  return { T: "10", J: "J", Q: "Q", K: "K", A: "A" }[value] || value;
}

function suit(value: string) {
  return { C: "♣", D: "♦", H: "♥", S: "♠" }[value] || "";
}

function phaseLabel(phase: string) {
  return { lobby: "等待开局", preflop: "翻牌前下注", flop: "翻牌圈", turn: "转牌圈", river: "河牌圈", showdown: "摊牌结算" }[phase] || phase;
}

createRoot(document.getElementById("root")!).render(<App />);
