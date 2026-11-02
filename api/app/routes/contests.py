"""Nickname proposals, votes, contest boards, and the activity summary."""

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.modules import accounts, contests
from app.modules.contests import activity
from app.routes.deps import (
    WRITE_ERRORS,
    CurrentUser,
    PlaceId,
    SessionCookie,
    SessionDep,
    errors,
    viewer,
)

router = APIRouter()


class ProposalRequest(BaseModel):
    place_id: int
    text: str = Field(min_length=1, max_length=60)


class ProposalResponse(BaseModel):
    id: int
    text: str
    agree: int
    disagree: int
    score: int
    is_incumbent: bool
    #: True when the signed-in viewer wrote it; they cannot vote for their own.
    is_yours: bool = False


class VoteRequest(BaseModel):
    proposal_id: int
    value: int = Field(ge=-1, le=1)


class ContestBoard(BaseModel):
    place_id: int
    nickname: str | None
    leading_candidate: str | None
    closes_at: datetime | None
    reopens_at: datetime | None
    quorum: int
    proposals: list[ProposalResponse]


@router.post("/api/proposals", status_code=201, responses=errors(401, 422, *WRITE_ERRORS))
async def create_proposal(
    body: ProposalRequest, session: SessionDep, user: CurrentUser
) -> ProposalResponse:
    try:
        proposal = await contests.propose(session, body.place_id, user.id, body.text)
    except contests.ProposalRejectedError:
        raise HTTPException(status_code=422, detail="That nickname cannot be used") from None

    await session.commit()
    return ProposalResponse(
        id=proposal.id,
        text=proposal.text,
        agree=proposal.agree,
        disagree=proposal.disagree,
        score=proposal.agree - proposal.disagree,
        is_incumbent=proposal.is_incumbent,
    )


@router.post("/api/votes", status_code=204, responses=errors(401, 403, 409, *WRITE_ERRORS))
async def cast_vote(body: VoteRequest, session: SessionDep, user: CurrentUser) -> Response:
    try:
        await contests.vote(session, body.proposal_id, user.id, body.value)
    except contests.SelfVoteError:
        raise HTTPException(
            status_code=403, detail="You cannot vote for your own proposal"
        ) from None
    except contests.NotEligibleToVoteError:
        raise HTTPException(
            status_code=403,
            detail="Voting opens once your account is two days old and you have found a place",
        ) from None
    except contests.ContestClosedError:
        raise HTTPException(status_code=409, detail="This contest has closed") from None

    await session.commit()
    return Response(status_code=204)


_YOUR_PROPOSALS = text("SELECT id FROM proposals WHERE place_id = :place_id AND user_id = :user_id")


@router.get("/api/contests/{place_id}")
async def read_contest(
    place_id: PlaceId, session: SessionDep, namescape_session: SessionCookie = None
) -> ContestBoard:
    state = await contests.state_for(session, place_id)
    signed_in = await viewer(session, namescape_session)
    yours: set[int] = set()
    if signed_in is not None:
        rows = await session.execute(
            _YOUR_PROPOSALS, {"place_id": place_id, "user_id": signed_in.user_id}
        )
        yours = {int(row[0]) for row in rows}
    return ContestBoard(
        place_id=state.place_id,
        nickname=state.nickname,
        leading_candidate=state.leading_candidate,
        closes_at=state.closes_at,
        reopens_at=state.reopens_at,
        quorum=state.quorum,
        proposals=[ProposalResponse(**asdict(p), is_yours=p.id in yours) for p in state.proposals],
    )


class ActivityResponse(BaseModel):
    """What the chrome needs to show a reason to return, in one request."""

    contests_closing_soon: int
    #: None when nobody is signed in.
    streak_days: int | None
    streak_at_risk: bool


@router.get("/api/activity")
async def read_activity(
    session: SessionDep, namescape_session: SessionCookie = None
) -> ActivityResponse:
    signed_in = await viewer(session, namescape_session)

    streak_days: int | None = None
    at_risk = False
    if signed_in is not None:
        mine = await accounts.passport(session, signed_in.username)
        if mine is not None:
            streak_days = mine.streak_days
            at_risk = mine.streak_at_risk

    return ActivityResponse(
        contests_closing_soon=await activity.closing_soon(session),
        streak_days=streak_days,
        streak_at_risk=at_risk,
    )
