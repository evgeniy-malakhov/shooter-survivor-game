from __future__ import annotations

from shared.ai.squads import SquadMode
from shared.models import ClientCommand, PlayerState, Vec2
from shared.systems.commands.base_handler import CommandHandler
from shared.tactical_gameplay import CompanionCommandKind, CompanionCommandState
from shared.world.world_context import WorldContext
from shared.world.world_state import WorldState


class SquadCommandHandler(CommandHandler):
    def handle(
        self,
        state: WorldState,
        ctx: WorldContext,
        player: PlayerState,
        command: ClientCommand,
    ) -> tuple[bool, str]:
        raw = str(command.payload.get("command", "follow"))
        try:
            kind = CompanionCommandKind(raw)
        except ValueError:
            return False, "invalid_squad_command"
        raw_target = command.payload.get("target_pos")
        target_pos = Vec2.from_dict(raw_target) if isinstance(raw_target, dict) else player.pos.copy()
        state.companion_commands[player.id] = CompanionCommandState(
            player_id=player.id,
            command=kind,
            target_pos=target_pos,
            issued_at=state.time,
            expires_at=state.time + 120.0,
        )
        if player.squad_id and player.squad_id in state.squads:
            squad = state.squads[player.squad_id]
            if kind == CompanionCommandKind.FOLLOW:
                squad.intent.mode = SquadMode.REGROUP
                squad.intent.target_pos = player.pos.copy()
            elif kind == CompanionCommandKind.HOLD:
                squad.intent.mode = SquadMode.HOLD_POSITION
                squad.intent.target_pos = target_pos
            elif kind == CompanionCommandKind.REGROUP:
                squad.intent.mode = SquadMode.REGROUP
                squad.intent.target_pos = player.pos.copy()
            elif kind == CompanionCommandKind.BREACH:
                squad.intent.mode = SquadMode.INVESTIGATE_SOUND
                squad.intent.target_pos = target_pos
            elif kind == CompanionCommandKind.SUPPRESS:
                squad.intent.mode = SquadMode.ENGAGE_TARGET
                squad.intent.target_pos = target_pos
            elif kind == CompanionCommandKind.HEAL:
                squad.intent.mode = SquadMode.EVACUATE_WOUNDED
                squad.intent.target_pos = player.pos.copy()
            elif kind == CompanionCommandKind.SILENT:
                squad.intent.mode = SquadMode.PATROL
                squad.intent.target_pos = target_pos
            squad.intent.expires_at = state.time + 18.0
        player.notice = f"squad.command.{kind.value}"
        player.notice_timer = 1.8
        return True, "squad_commanded"
