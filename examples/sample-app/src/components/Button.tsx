import React from "react";
import type { FC } from "react";
import { formatLabel } from "../utils/format";

interface ButtonProps {
  label: string;
}

const Button: FC<ButtonProps> = ({ label }) => {
  return <button>{formatLabel(label)}</button>;
};

export default Button;
