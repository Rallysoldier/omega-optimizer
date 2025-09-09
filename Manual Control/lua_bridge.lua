-- === HD2 Multi-Feature Bridge (int+float, NO FALLBACK) ===
-- Reads key=value lines from C:\Users\Public\hd2_bridge.txt and writes to CE memory records.

local BRIDGE_FILE = [[C:\Users\Public\hd2_bridge.txt]]
local POLL_MS     = 200
local VERBOSE     = false   -- set true to see console logs

-- Per-feature rules
-- kind = "int" | "float"; decimals used only for "float"
local FEATURES = {
  ["Enter Firerate For Force Apply"] = { min = 1000, max = 5000, kind = "float", decimals = 3 },
  ["Enemy Multiplier"]               = { min = 1.5,  max = 500,  kind = "float", decimals = 2 },
}

if multiBridgeTimer then multiBridgeTimer.destroy(); multiBridgeTimer = nil end

local al = getAddressList()
local lastStr = {}
local warned_no_file, warned_no_kv = false, false
local warned_no_mr = {}

local function log(...) if VERBOSE then print(...) end end
local function clamp_num(v, r) if r then if r.min and v<r.min then v=r.min end; if r.max and v>r.max then v=r.max end end; return v end
local function format_num(v, r) if not r or r.kind=="float" then local d=(r and r.decimals) or 2; return string.format("%."..d.."f", v) else return string.format("%d", math.floor(v+0.5)) end end

local function read_kv_file(path)
  local f = io.open(path, "r"); if not f then return nil end
  local t = {}
  for line in f:lines() do
    if not line:match("^%s*[#;]") and not line:match("^%s*%-%-") then
      local k, v = line:match("^%s*(.-)%s*=%s*(.-)%s*$")
      if k and v then
        local numtok = v:match("[-+]?%d+%.?%d*") or v:match("[-+]?%.%d+")
        if numtok then t[k] = tonumber(numtok) end
      end
    end
  end
  f:close()
  return t
end

multiBridgeTimer = createTimer()
multiBridgeTimer.Interval = POLL_MS
multiBridgeTimer.OnTimer = function(_)
  local kv = read_kv_file(BRIDGE_FILE)
  if not kv then
    if not warned_no_file then print("[HD2 Bridge] File not found or unreadable: "..BRIDGE_FILE); warned_no_file=true end
    return
  end
  local any=false; for _ in pairs(kv) do any=true break end
  if not any then
    if not warned_no_kv then print("[HD2 Bridge] No valid key=value lines in: "..BRIDGE_FILE); warned_no_kv=true end
    return
  end

  for desc, rules in pairs(FEATURES) do
    local raw = kv[desc]
    if raw ~= nil then
      local mr = al.getMemoryRecordByDescription(desc)
      if mr then
        warned_no_mr[desc] = nil
        local v = clamp_num(raw, rules)
        local s = format_num(v, rules)
        if lastStr[desc] ~= s then mr.Value = s; lastStr[desc] = s; log(string.format("[HD2 Bridge] %s = %s", desc, s)) end
      elseif not warned_no_mr[desc] then
        print("[HD2 Bridge] Memory record not found (check Description/Type): "..desc)
        warned_no_mr[desc] = true
      end
    end
  end
end

print("HD2 Bridge active. Watching:", BRIDGE_FILE)
-- Ensure CE records exist (Type=Float) and Descriptions match exactly.
