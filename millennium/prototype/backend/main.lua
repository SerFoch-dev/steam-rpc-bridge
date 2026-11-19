local millennium = require("millennium")

local function on_load()
    -- Backend stub. The current prototype helper is launched manually from a terminal.
    millennium.ready()
end

return { on_load = on_load }
