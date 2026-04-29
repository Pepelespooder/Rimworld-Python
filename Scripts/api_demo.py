log("<color=#c678dd><b>API demo:</b></color> <color=#f8f8f2>program_state = " + rim.program_state() + "</color>")
log("<color=#c678dd><b>API demo:</b></color> <color=#f8f8f2>latest_save = " + rim.latest_save_name() + "</color>")
log("<color=#c678dd><b>API demo:</b></color> <color=#f8f8f2>thing_defs = " + str(rim.thing_def_count()) + "</color>")

if rim.game_loaded():
    log("<color=#c678dd><b>API demo:</b></color> <color=#a6e22e>" + rim.colony_summary() + "</color>")
    log("<color=#c678dd><b>API demo:</b></color> <color=#66d9ef>selected pawn: " + rim.selected_pawn_name() + "</color>")
else:
    log("<color=#c678dd><b>API demo:</b></color> <color=#75715e>No game loaded yet. In a loaded map, try rim.spawn_near_selected('Steel', 75).</color>")
