/**
 * Minimal dense linear algebra for the three-state battery filter.
 *
 * Matrices are plain row-major arrays. The sizes are tiny (3x3 at most), so a
 * dependency-free implementation is clearer than a general library here.
 */
export type Matrix = number[][];

export function zeros(rows: number, cols: number): Matrix {
  return Array.from({ length: rows }, () => Array.from({ length: cols }, () => 0));
}

export function identity(size: number): Matrix {
  const result = zeros(size, size);
  for (let i = 0; i < size; i += 1) result[i][i] = 1;
  return result;
}

export function diagonal(values: readonly number[]): Matrix {
  const result = zeros(values.length, values.length);
  values.forEach((value, index) => {
    result[index][index] = value;
  });
  return result;
}

export function multiply(a: Matrix, b: Matrix): Matrix {
  const rows = a.length;
  const inner = a[0]?.length ?? 0;
  const cols = b[0]?.length ?? 0;
  if (inner !== b.length) {
    throw new Error(`Matrix shape mismatch: ${rows}x${inner} times ${b.length}x${cols}`);
  }
  const result = zeros(rows, cols);
  for (let i = 0; i < rows; i += 1) {
    for (let k = 0; k < inner; k += 1) {
      const av = a[i][k];
      if (av === 0) continue;
      for (let j = 0; j < cols; j += 1) {
        result[i][j] += av * b[k][j];
      }
    }
  }
  return result;
}

export function transpose(a: Matrix): Matrix {
  const rows = a.length;
  const cols = a[0]?.length ?? 0;
  const result = zeros(cols, rows);
  for (let i = 0; i < rows; i += 1) {
    for (let j = 0; j < cols; j += 1) {
      result[j][i] = a[i][j];
    }
  }
  return result;
}

export function addMatrix(a: Matrix, b: Matrix): Matrix {
  return a.map((row, i) => row.map((value, j) => value + b[i][j]));
}

export function subtractMatrix(a: Matrix, b: Matrix): Matrix {
  return a.map((row, i) => row.map((value, j) => value - b[i][j]));
}

export function scaleMatrix(a: Matrix, scalar: number): Matrix {
  return a.map((row) => row.map((value) => value * scalar));
}

export function matrixVector(a: Matrix, vector: readonly number[]): number[] {
  return a.map((row) => row.reduce((sum, value, index) => sum + value * vector[index], 0));
}

export function outer(a: readonly number[], b: readonly number[]): Matrix {
  return a.map((av) => b.map((bv) => av * bv));
}

export function invert2(matrix: Matrix): Matrix {
  const [[a, b], [c, d]] = matrix;
  const determinant = a * d - b * c;
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12) {
    throw new Error("2x2 matrix is singular");
  }
  return [
    [d / determinant, -b / determinant],
    [-c / determinant, a / determinant],
  ];
}

export function symmetrize(matrix: Matrix): Matrix {
  const transposed = transpose(matrix);
  return addMatrix(matrix, transposed).map((row) => row.map((value) => value / 2));
}

export function allFinite(matrix: Matrix): boolean {
  return matrix.every((row) => row.every((value) => Number.isFinite(value)));
}

export function dot(a: readonly number[], b: readonly number[]): number {
  return a.reduce((sum, value, index) => sum + value * b[index], 0);
}

export function quadraticForm(vector: readonly number[], matrix: Matrix): number {
  return dot(vector, matrixVector(matrix, vector));
}
