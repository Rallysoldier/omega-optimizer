-- === HD2 Fire Rate Bridge ===
-- Reads a number from a text file and writes it to the memory record
-- named exactly: "Enter Firerate For Force Apply"

local BRIDGE_FILE = [[C:\Users\Public\hd2_fire_rate.txt]]
local TARGET_DESC = "Enter Firerate For Force Apply"

local al = getAddressList()
local mr = al.getMemoryRecordByDescription(TARGET_DESC)

if not mr then
  showMessage("Lua bridge: can't find memory record with description: "..TARGET_DESC)
else
  if bridgeTimer ~= nil then
    bridgeTimer.destroy()
  end

  bridgeTimer = createTimer()
  bridgeTimer.Interval = 200 -- ms
  bridgeTimer.OnTimer = function(t)
    local f = io.open(BRIDGE_FILE, "r")
    if f then
      local data = f:read("*all")
      f:close()
      local v = tonumber(data)
      if v and v == v and v > 0 then
        -- CE memory record .Value expects string; formats float OK
        mr.Value = string.format("%.3f", v)
      end
    end
  end
end
