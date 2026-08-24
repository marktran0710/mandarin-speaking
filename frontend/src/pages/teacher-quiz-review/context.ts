import { createContext, useContext } from "react";

export const QuizReviewContext = createContext<any>(null);
export const useQuizReviewContext = () => useContext(QuizReviewContext);
