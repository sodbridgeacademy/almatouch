from flask import request, redirect, render_template, session, Blueprint, url_for, flash
from models import Organization, OrgInvite, User, Event, MessageTemplate, Question, Department, UserDepartment
from extensions import db, bcrypt
from datetime import datetime, timedelta
import secrets
import uuid


# Org Blueprint
dept_bp = Blueprint("dept", __name__)


# DEPT ROUTES
@dept_bp.route("/org/departments/create", methods=["POST", "GET"])
def create_department():

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description")

    if not name:
        flash("Department name is required", "error")
        return redirect(request.referrer)

    # prevent duplicates
    exists = Department.query.filter_by(org_id=org_id, name=name).first()
    if exists:
        flash("Department already exists", "error")
        return redirect(request.referrer)

    dept = Department(
        org_id=org_id,
        name=name,
        description=description
    )

    db.session.add(dept)
    db.session.commit()

    flash("Department created successfully", "success")
    return redirect(url_for("dept.list_departments"))


@dept_bp.route("/org/departments/<int:dept_id>/update", methods=["POST"])
def update_department(dept_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    dept = Department.query.filter_by(id=dept_id, org_id=org_id).first_or_404()

    name = request.form.get("name", "").strip()
    description = request.form.get("description")

    if not name:
        flash("Department name is required", "error")
        return redirect(request.referrer)

    dept.name = name
    dept.description = description

    db.session.commit()

    flash("Department updated successfully", "success")
    return redirect(url_for("dept.list_departments"))


@dept_bp.route("/org/departments/<int:dept_id>/delete", methods=["POST"])
def delete_department(dept_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    dept = Department.query.filter_by(id=dept_id, org_id=org_id).first_or_404()

    # prevent delete if users exist
    if dept.users:
        flash("Cannot delete department with active users", "error")
        return redirect(request.referrer)

    db.session.delete(dept)
    db.session.commit()

    flash("Department deleted successfully", "success")
    return redirect(url_for("dept.list_departments"))


@dept_bp.route("/org/departments11")
def list_departments11():

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    departments = Department.query.filter_by(org_id=org_id).all()

    return render_template("departments.html", departments=departments)


@dept_bp.route("/org/departments")
def list_departments():

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    departments = Department.query.filter_by(org_id=org_id).all()

    # =========================
    # ATTACH MEMBER COUNTS
    # =========================
    dept_ids = [d.id for d in departments]

    if dept_ids:
        counts = (
            db.session.query(
                UserDepartment.department_id,
                db.func.count(UserDepartment.user_id)
            )
            .filter(UserDepartment.department_id.in_(dept_ids))
            .group_by(UserDepartment.department_id)
            .all()
        )

        # convert to dictionary for fast lookup
        count_map = {dept_id: count for dept_id, count in counts}

    else:
        count_map = {}

    # attach to each department object
    for dept in departments:
        dept.member_count = count_map.get(dept.id, 0)

    return render_template(
        "departments.html",
        departments=departments
    )


# @dept_bp.route("/departments/<int:dept_id>")
# def department_detail1(dept_id):

#     org_id = session.get("org_id")
#     if not org_id:
#         return redirect(url_for("org.org_login"))

#     user_id = session.get("user_id")

#     if not user_id:
#         return redirect(url_for("org.org_login"))

#     user = User.query.get(user_id)

#     dept = Department.query.filter_by(id=dept_id, org_id=org_id).first_or_404()

#     #members = User.query.filter_by(departments__id=dept.id).all()
#     #members = (User.query.join(UserDepartment).filter(UserDepartment.department_id == dept.id).all())
#     members = Department.query.filter(members = user.id).all()
#     print(f"dept members: {members}")

#     return render_template(
#         "department_detail.html",
#         dept=dept,
#         members=members
#     )

@dept_bp.route("/departments1/<int:dept_id>")
def department_detail22(dept_id):

    org_id = session.get("org_id")
    if not org_id:
        return redirect(url_for("org.org_login"))

    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("org.org_login"))

    user = User.query.get(user_id)

    print("User DepartmentS...", UserDepartment.query.all())

    memberships = UserDepartment.query.all()

    for m in memberships:
        print(
            f"user_id={m.user_id}, "
            f"department_id={m.department_id}"
        )

        dept = Department.query.filter_by(
            id=dept_id,
            org_id=org_id
        ).first_or_404()

    # ✅ CORRECT WAY: get members of department
    # members = (
    #     User.query
    #     .join(UserDepartment)
    #     .filter(UserDepartment.department_id == dept.id)
    #     .all()
    # )

    members = (
    User.query
    .join(UserDepartment, User.id == UserDepartment.user_id)
    .filter(UserDepartment.department_id == dept.id)
    .all()
    )

    print(f"dept members: {members}")

    print(UserDepartment.query.all())

    return render_template(
        "department_detail.html",
        dept=dept,
        members=members
    )


@dept_bp.route("/departments33/<int:dept_id>")
def department_detail33(dept_id):

    org_id = session.get("org_id")
    user_id = session.get("user_id")

    if not org_id or not user_id:
        return redirect(url_for("org.org_login"))

    # 1. Get department
    dept = Department.query.filter_by(
        id=dept_id,
        org_id=org_id
    ).first_or_404()

    # 2. DEBUG: confirm memberships exist
    memberships = UserDepartment.query.filter_by(
        department_id=dept.id
    ).all()

    print("=== MEMBERSHIPS ===")
    for m in memberships:
        print(m.user_id, m.department_id)

    # 3. Get users in department (CLEAN QUERY)
    members = (
        User.query
        .join(UserDepartment, User.id == UserDepartment.user_id)
        .filter(UserDepartment.department_id == dept.id)
        .all()
    )

    print("=== MEMBERS FOUND ===", members)

    return render_template(
        "department_detail.html",
        dept=dept,
        members=members
    )


@dept_bp.route("/departments/<int:dept_id>")
def department_detail(dept_id):

    org_id = session.get("org_id")
    user_id = session.get("user_id")

    if not org_id or not user_id:
        return redirect(url_for("org.org_login"))

    # =========================
    # GET DEPARTMENT (SAFE)
    # =========================
    dept = Department.query.filter_by(
        id=dept_id,
        org_id=org_id
    ).first_or_404()

    # =========================
    # GET MEMBERS (CLEAN MANY-TO-MANY JOIN)
    # =========================
    members = (
        User.query
        .join(UserDepartment, User.id == UserDepartment.user_id)
        .filter(UserDepartment.department_id == dept.id)
        .all()
    )

    print(f"Department: {dept.name}")
    print(f"Members count: {len(members)}")

    return render_template(
        "department_detail.html",
        dept=dept,
        members=members
    )

'''
@user_bp.route("/user/onboarding", methods=["GET", "POST"])
def user_onboarding1():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("org.org_login"))

    user = User.query.get(user_id)

    if request.method == "POST":

        user.first_name = request.form.get("first_name")
        user.last_name = request.form.get("last_name")
        user.date_of_birth = request.form.get("dob")
        user.department = request.form.get("department")
        user.message_frequency = request.form.get("message_frequency")

        # optional
        user.gender = request.form.get("gender")
        user.marital_status = request.form.get("marital_status")
        user.religion = request.form.get("religion")
        user.nationality = request.form.get("nationality")

        user.is_onboarded = True

        db.session.commit()

        return redirect(url_for("user.user_dashboard"))

    return render_template("user_onboarding.html", user=user)

'''