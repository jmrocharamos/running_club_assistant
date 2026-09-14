from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.survey import Survey
from app.models.user import User
from app.schemas.survey import RunningPlanSurveyAnswers, SurveyCreate, SurveyRead
from pydantic import BaseModel

router = APIRouter(prefix='/surveys', tags=['Surveys'])


@router.get('/forms/running-plan')
def get_running_plan_survey_form(current_user: User = Depends(get_current_user)):
    return RunningPlanSurveyAnswers.model_json_schema()


# Accept the slashless URL used by the frontend proxy without redirecting.
@router.post('', response_model=SurveyRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post('/', response_model=SurveyRead, status_code=status.HTTP_201_CREATED)
def create_survey(
        survey_data: SurveyCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    answers = (
        survey_data.answers.model_dump(mode="json")
        if isinstance(survey_data.answers, BaseModel)
        else survey_data.answers
    )

    survey = Survey(
        user_id=current_user.id,
        survey_type=survey_data.survey_type,
        answers=answers,
    )

    db.add(survey)
    db.commit()
    db.refresh(survey)

    return survey


# Accept the slashless URL used by the frontend proxy without redirecting.
@router.get('', response_model=list[SurveyRead], include_in_schema=False)
@router.get('/', response_model=list[SurveyRead])
def get_surveys(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    return db.scalars(
        select(Survey)
        .where(Survey.user_id == current_user.id, Survey.deleted_at.is_(None))
        .order_by(Survey.created_at.desc())
    ).all()


@router.get('/latest', response_model=SurveyRead)
def get_latest_survey(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    survey = db.scalars(
        select(Survey)
        .where(Survey.user_id == current_user.id, Survey.deleted_at.is_(None))
        .order_by(Survey.created_at.desc())
        .limit(1)
    ).first()

    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No surveys found for this user',
        )

    return survey


def _get_owned_survey(survey_id: UUID, current_user: User, db: Session) -> Survey:
    survey = db.get(Survey, survey_id)

    if not survey or survey.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Survey not found',
        )

    return survey


@router.get('/{survey_id}', response_model=SurveyRead)
def get_survey(
        survey_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    return _get_owned_survey(survey_id, current_user, db)


@router.delete('/{survey_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_survey(
        survey_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    survey = _get_owned_survey(survey_id, current_user, db)

    if survey.deleted_at is None:
        survey.deleted_at = datetime.now(timezone.utc)
        db.commit()

    return None
