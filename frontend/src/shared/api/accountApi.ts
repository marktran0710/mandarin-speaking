/** Account API boundary for independent student/teacher/admin surfaces. */
export {
  createStudent,
  createTeacher,
  deleteStudent,
  deleteTeacher,
  listStudents,
  listTeachers,
  loginAdmin,
  loginStudent,
  loginTeacher,
  logoutAdmin,
  logoutTeacher,
  updateStudent,
  updateTeacher,
} from "../../services/database";

export type { Student, Teacher } from "../../services/database";
