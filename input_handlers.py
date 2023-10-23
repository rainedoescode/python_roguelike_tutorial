from __future__ import annotations

from typing import Optional, TYPE_CHECKING
import tcod
from tcod import libtcodpy

import actions
from actions import (
    Action,
    BumpAction,
    PickupAction,
    WaitAction,
)
import color
from entity import Item
import exceptions

import tcod.event

if TYPE_CHECKING:
    from engine import Engine
    from entity import Item


MOVE_KEYS = {
    # Arrow keys
    tcod.event.KeySym.UP: (0, -1),
    tcod.event.KeySym.DOWN: (0, 1),
    tcod.event.KeySym.LEFT: (-1, 0),
    tcod.event.KeySym.RIGHT: (1, 0),
    tcod.event.KeySym.HOME: (-1, -1),
    tcod.event.KeySym.END: (-1, 1),
    tcod.event.KeySym.PAGEUP: (1, -1),
    tcod.event.KeySym.PAGEDOWN: (1, 1),
    # Numpad keys
    tcod.event.KeySym.KP_8: (0, -1),
    tcod.event.KeySym.KP_2: (0, 1),
    tcod.event.KeySym.KP_4: (-1, 0),
    tcod.event.KeySym.KP_6: (1, 0),
    tcod.event.KeySym.KP_7: (-1, -1),
    tcod.event.KeySym.KP_1: (-1, 1),
    tcod.event.KeySym.KP_9: (1, -1),
    tcod.event.KeySym.KP_3: (1, 1),
    # Vi keys
    tcod.event.KeySym.k: (0, -1),
    tcod.event.KeySym.j: (0, 1),
    tcod.event.KeySym.h: (-1, 0),
    tcod.event.KeySym.l: (1, 0),
    tcod.event.KeySym.y: (-1, -1),
    tcod.event.KeySym.b: (-1, 1),
    tcod.event.KeySym.u: (1, -1),
    tcod.event.KeySym.n: (1, 1),
}

WAIT_KEYS = {
    tcod.event.KeySym.PERIOD,
    tcod.event.KeySym.KP_5,
    tcod.event.KeySym.CLEAR,
}

CONFIRM_KEYS = {
    tcod.event.KeySym.RETURN,
    tcod.event.KeySym.KP_ENTER
}


class EventHandler(tcod.event.EventDispatch[Action]):
    def __init__(self, engine: Engine):
        self.engine = engine


    def handle_events(self, event: tcod.event.Event) -> None:
        self.handle_action(self.dispatch(event))


    def handle_action(self, action: Optional[Action]) -> bool:
        """Handle actions returned from event methods
        Returns True if the action will advance a turn
        """
        if action is None:
            return False
        
        try:
            action.perform()
        except exceptions.Impossible as exc:
            self.engine.message_log.add_message(exc.args[0], color.impossible)
            return False # Skip enemy turn on exceptions
        
        self.engine.handle_enemy_turns()

        self.engine.update_fov()
        return True

    
    def ev_mousemotion(self, event: tcod.event.MouseMotion) -> None:
        if self.engine.game_map.in_bounds(event.tile.x, event.tile.y):
            self.engine.mouse_location = event.tile.x, event.tile.y
    

    def ev_quit(self, event: tcod.event.Quit) -> Optional[Action]:
        raise SystemExit()
    

    def on_render(self, console: tcod.console.Console) -> None:
        self.engine.render(console)


class AskUserEventHandler(EventHandler):
    """
    Handles user input for actions which require special input
    """
    def handle_action(self, action: Optional[Action]) -> bool:
        """
        Return to the main event handler when valid action performed
        """
        if super().handle_action(action):
            self.engine.event_handler = MainGameEventHandler(self.engine)
            return True
        return False
    

    def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[Action]:
        """By default, any key exits this input handler"""
        # Ignore modifier keys
        if event.sym in {
            tcod.event.KeySym.LSHIFT,
            tcod.event.KeySym.RSHIFT,
            tcod.event.KeySym.LCTRL,
            tcod.event.KeySym.RCTRL,
            tcod.event.KeySym.LALT,
            tcod.event.KeySym.RALT,
        }:
            return None
        return self.on_exit()
    

    def ev_mousebuttondown(self, event: tcod.event.MouseButtonDown) -> Optional[Action]:
        """By default, any mouse click exits this input handler"""
        return self.on_exit()
    

    def on_exit(self):
        """
        Called when the user is trying to exit or cancel an action.
        By default, returns to main event handler
        """
        self.engine.event_handler = MainGameEventHandler(self.engine)
        return None


class InventoryEventHandler(AskUserEventHandler):
    """
    This handler lets the user select an item
    Subclass determines behavior
    """
    TITLE = "<missing title>"

    def on_render(self, console: tcod.console.Console) -> None:
        """
        Render an inventory menu which displays items in inventory
        and the letter to select them. Will change position depending
        on where the player is located to prevent hiding the player
        """
        super().on_render(console)
        number_of_items_in_inventory = len(self.engine.player.inventory.items)

        height = number_of_items_in_inventory + 2

        if height <= 3:
            height = 3

        if self.engine.player.x <= 30:
            x = 40
        else:
            x = 0

        y = 0

        width = len(self.TITLE) + 4

        console.draw_frame(
            x=x,
            y=y,
            width=width,
            height=height,
            title=self.TITLE,
            clear=True,
            fg=(255, 255, 255),
            bg=(0, 0, 0),
        )

        if number_of_items_in_inventory > 0:
            for i, item in enumerate(self.engine.player.inventory.items):
                item_key = chr(ord("a") + i)
                console.print(x + 1, y + i + 1, f"({item_key}) {item.name}")
        else:
            console.print(x + 1, y + 1, "(Empty)")

    def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[Action]:
        player = self.engine.player
        key = event.sym
        index = key - tcod.event.KeySym.a

        if 0 <= index <= 26:
            try:
                selected_item = player.inventory.items[index]
            except IndexError:
                self.engine.message_log.add_message("Invalid entry", color.invalid)
                return None
            return self.on_item_selected(selected_item)
        return super().ev_keydown(event)
    
    def on_item_selected(self, item: Item) -> Optional[Action]:
        """
        Called when user selects a valid item
        """
        raise NotImplementedError()


class InventoryActivateHandler(InventoryEventHandler):
    """Handle using an item in inventory"""

    TITLE = "Select an item to use"

    def on_item_selected(self, item: Item) -> Optional[Action]:
        """Return the action for the selected item"""
        return item.consumable.get_action(self.engine.player)
    

class InventoryDropHandler(InventoryEventHandler):
    """Handle dropping an inventory item"""

    TITLE = "Select an item to drop"

    def on_item_selected(self, item: Item) -> Optional[Action]:
        """Drop this item"""
        return actions.DropItem(self.engine.player, item)


class SelectIndexHandler(AskUserEventHandler):
    """
    Handles asking the user for an index on the map
    """

    def __init__(self, engine: Engine):
        """
        Sets the cursor to the player when this handler is constructed
        """
        super().__init__(engine)
        player = self.engine.player
        engine.mouse_location = player.x, player.y

    def on_render(self, console: tcod.console.Console) -> None:
        """Highlight the tile under the cursor."""
        super().on_render(console)
        x, y = self.engine.mouse_location
        console.tiles_rgb["bg"][x, y] = color.white
        console.tiles_rgb["fg"][x, y] = color.black

    def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[Action]:
        """Check for movement or confirmation keys"""
        key = event.sym

        if key in MOVE_KEYS:
            modifier = 1 # Holding modifier keys will speed up key movement
            if event.mod & (tcod.event.KeySym.LSHIFT | tcod.event.KeySym.RSHIFT):
                modifier *= 5
            if event.mod & (tcod.event.KeySym.LCTRL | tcod.event.KeySym.RCTRL):
                modifier *= 10
            if event.mod & (tcod.event.KeySym.LALT | tcod.event.KeySym.RALT):
                modifier *= 20
            
            x, y = self.engine.mouse_location
            dx, dy = MOVE_KEYS[key]
            x += dx * modifier
            y += dy * modifier
            # Clamp cursor index to map size
            x = max(0, min(x, self.engine.game_map.width -1))
            y = max(0, min(y, self.engine.game_map.height -1))
            self.engine.mouse_location = x, y
            return None
        
        elif key in CONFIRM_KEYS:
            return self.on_index_selected(*self.engine.mouse_location)
        return super().ev_keydown(event)
    
    def ev_mousebuttondown(self, event: tcod.event.MouseButtonDown) -> Optional[Action]:
        """Left click confirms a selection"""

        if self.engine.game_map.in_bounds(*event.tile):
            if event.button == 1:
                return self.on_index_selected(*event.tile)
            
        return super().ev_mousebuttondown(event)
    
class LookHandler(SelectIndexHandler):
    """Allows palyer to look around the map using the keyboard"""

    def on_index_selected(self, x: int, y: int) -> None:
        """Return to main handler"""
        self.engine.event_handler = MainGameEventHandler(self.engine)


#---------------------#
#  Main Game Handler  #
#---------------------#
class MainGameEventHandler(EventHandler):    
    
    def ev_keydown(self, event:tcod.event.KeyDown) -> Optional[Action]:
        action: Optional[Action] = None

        key = event.sym

        player = self.engine.player

        if key in MOVE_KEYS:
            dx, dy = MOVE_KEYS[key]
            action = BumpAction(player, dx, dy)

        elif key in WAIT_KEYS:
            action = WaitAction(player)

        elif key == tcod.event.KeySym.ESCAPE:
            raise SystemExit()

        elif key == tcod.event.KeySym.v:
            self.engine.event_handler = HistoryViewer(self.engine)

        elif key == tcod.event.KeySym.g:
            action = PickupAction(player)

        elif key == tcod.event.KeySym.i:
            self.engine.event_handler = InventoryActivateHandler(self.engine)
        elif key == tcod.event.KeySym.d:
            self.engine.event_handler = InventoryDropHandler(self.engine)

        elif key == tcod.event.KeySym.SLASH:
            self.engine.event_handler = LookHandler(self.engine)

        # No valid key press
        return action


class GameOverEventHandler(EventHandler):

    def ev_keydown(self, event: tcod.event.KeyDown) -> Optional[Action]:
        if event.sym == tcod.event.KeySym.ESCAPE:
            raise SystemExit()


CURSOR_Y_KEYS = {
    tcod.event.KeySym.UP: -1,
    tcod.event.KeySym.DOWN: 1,
    tcod.event.KeySym.PAGEUP: -10,
    tcod.event.KeySym.PAGEDOWN: 10,
}


class HistoryViewer(EventHandler):
    """Print the history on a larger window which can be navigated"""

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self.log_length = len(engine.message_log.messages)
        self.cursor = self.log_length - 1

    
    def on_render(self, console: tcod.console.Console) -> None:
        super().on_render(console) # Draw main state as background

        log_console = tcod.console.Console(console.width - 6, console.height - 6)

        # Draw a frame with custom banner title
        log_console.draw_frame(0, 0, log_console.width, log_console.height)
        log_console.print_box(
            0, 0, log_console.width, 1, "┤Message history├", alignment=libtcodpy.CENTER
        )

        # Render the message log using the cursor parameter
        self.engine.message_log.render_messages(
            log_console,
            1,
            1,
            log_console.width - 2,
            log_console.height - 2,
            self.engine.message_log.messages[: self.cursor + 1],
        )
        log_console.blit(console, 3, 3)

    
    def ev_keydown(self, event: tcod.event.KeyDown) ->  None:
        # Conditional movement
        if event.sym in CURSOR_Y_KEYS:
            adjust = CURSOR_Y_KEYS[event.sym]
            if adjust < 0 and self.cursor == 0:
                # Only move from top to bottom when on the edge
                self.cursor = self.log_length - 1
            elif adjust > 0 and self.cursor == self.log_length - 1:
                # Same with bottom to top movement
                self.cursor = 0
            else:
                # Otherwise move while staying clamped to bounds of history log
                self.cursor = max(0, min(self.cursor + adjust, self.log_length - 1))
        elif event.sym == tcod.event.KeySym.HOME:
            self.cursor = 0 # Move directly to top message
        elif event.sym == tcod.event.KeySym.END:
            self.cursor = self.log_length - 1 # Move to last message
        else: # Any other key returns to main game state
            self.engine.event_handler = MainGameEventHandler(self.engine)
