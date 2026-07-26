package io.sqlflowmvp;

import java.util.ArrayList;
import java.util.Locale;

final class SqlText {
    private SqlText() {
    }

    static String maskLiteralsAndComments(String sql) {
        var masked = new StringBuilder(sql.length());
        var state = State.NORMAL;

        for (var i = 0; i < sql.length(); i++) {
            var ch = sql.charAt(i);
            var next = i + 1 < sql.length() ? sql.charAt(i + 1) : '\0';

            switch (state) {
                case NORMAL -> {
                    if (ch == '\'') {
                        masked.append(' ');
                        state = State.STRING;
                    } else if (ch == '-' && next == '-') {
                        masked.append("  ");
                        i++;
                        state = State.LINE_COMMENT;
                    } else if (ch == '/' && next == '*') {
                        masked.append("  ");
                        i++;
                        state = State.BLOCK_COMMENT;
                    } else {
                        masked.append(ch);
                    }
                }
                case STRING -> {
                    masked.append(ch == '\n' ? '\n' : ' ');
                    if (ch == '\'' && next == '\'') {
                        masked.append(' ');
                        i++;
                    } else if (ch == '\'') {
                        state = State.NORMAL;
                    }
                }
                case LINE_COMMENT -> {
                    masked.append(ch == '\n' ? '\n' : ' ');
                    if (ch == '\n') {
                        state = State.NORMAL;
                    }
                }
                case BLOCK_COMMENT -> {
                    if (ch == '*' && next == '/') {
                        masked.append("  ");
                        i++;
                        state = State.NORMAL;
                    } else {
                        masked.append(ch == '\n' ? '\n' : ' ');
                    }
                }
            }
        }
        return masked.toString();
    }

    static int matchingParen(String maskedSql, int openIndex) {
        var depth = 0;
        for (var i = openIndex; i < maskedSql.length(); i++) {
            var ch = maskedSql.charAt(i);
            if (ch == '(') {
                depth++;
            } else if (ch == ')' && --depth == 0) {
                return i;
            }
        }
        return -1;
    }

    static int statementEnd(String maskedSql, int start) {
        var depth = 0;
        for (var i = start; i < maskedSql.length(); i++) {
            var ch = maskedSql.charAt(i);
            if (ch == '(') {
                depth++;
            } else if (ch == ')') {
                depth = Math.max(0, depth - 1);
            } else if (ch == ';' && depth == 0) {
                return i;
            }
        }
        return maskedSql.length();
    }

    static int topLevelKeyword(String sql, String keyword, int fromIndex) {
        var masked = maskLiteralsAndComments(sql);
        var upper = masked.toUpperCase(Locale.ROOT);
        var target = keyword.toUpperCase(Locale.ROOT);
        var depth = 0;

        for (var i = Math.max(0, fromIndex); i <= upper.length() - target.length(); i++) {
            var ch = upper.charAt(i);
            if (ch == '(') {
                depth++;
                continue;
            }
            if (ch == ')') {
                depth = Math.max(0, depth - 1);
                continue;
            }
            if (depth != 0 || !upper.regionMatches(i, target, 0, target.length())) {
                continue;
            }
            var beforeOk = i == 0 || !isIdentifierPart(upper.charAt(i - 1));
            var afterIndex = i + target.length();
            var afterOk = afterIndex >= upper.length() || !isIdentifierPart(upper.charAt(afterIndex));
            if (beforeOk && afterOk) {
                return i;
            }
        }
        return -1;
    }

    static ArrayList<String> splitTopLevel(String value, char delimiter) {
        var parts = new ArrayList<String>();
        var current = new StringBuilder();
        var depth = 0;
        var inString = false;
        var inQuotedIdentifier = false;

        for (var i = 0; i < value.length(); i++) {
            var ch = value.charAt(i);
            var next = i + 1 < value.length() ? value.charAt(i + 1) : '\0';
            if (inString) {
                current.append(ch);
                if (ch == '\'' && next == '\'') {
                    current.append(next);
                    i++;
                } else if (ch == '\'') {
                    inString = false;
                }
                continue;
            }
            if (inQuotedIdentifier) {
                current.append(ch);
                if (ch == '"') {
                    inQuotedIdentifier = false;
                }
                continue;
            }
            if (ch == '\'') {
                inString = true;
                current.append(ch);
            } else if (ch == '"') {
                inQuotedIdentifier = true;
                current.append(ch);
            } else if (ch == '(') {
                depth++;
                current.append(ch);
            } else if (ch == ')') {
                depth = Math.max(0, depth - 1);
                current.append(ch);
            } else if (depth == 0 && ch == delimiter) {
                parts.add(current.toString());
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        parts.add(current.toString());
        return parts;
    }

    static ArrayList<String> splitTopLevelAnd(String value) {
        var parts = new ArrayList<String>();
        var masked = maskLiteralsAndComments(value);
        var upper = masked.toUpperCase(Locale.ROOT);
        var depth = 0;
        var start = 0;

        for (var i = 0; i < upper.length(); i++) {
            var ch = upper.charAt(i);
            if (ch == '(') {
                depth++;
            } else if (ch == ')') {
                depth = Math.max(0, depth - 1);
            } else if (depth == 0
                && upper.regionMatches(i, "AND", 0, 3)
                && (i == 0 || !isIdentifierPart(upper.charAt(i - 1)))
                && (i + 3 >= upper.length() || !isIdentifierPart(upper.charAt(i + 3)))) {
                parts.add(value.substring(start, i));
                start = i + 3;
                i += 2;
            }
        }
        parts.add(value.substring(start));
        return parts;
    }

    static String normalizeWhitespace(String value) {
        var out = new StringBuilder();
        var pendingSpace = false;
        var inString = false;

        for (var i = 0; i < value.length(); i++) {
            var ch = value.charAt(i);
            var next = i + 1 < value.length() ? value.charAt(i + 1) : '\0';
            if (inString) {
                out.append(ch);
                if (ch == '\'' && next == '\'') {
                    out.append(next);
                    i++;
                } else if (ch == '\'') {
                    inString = false;
                }
                continue;
            }
            if (ch == '\'') {
                if (pendingSpace && !out.isEmpty()) {
                    out.append(' ');
                }
                pendingSpace = false;
                inString = true;
                out.append(ch);
            } else if (Character.isWhitespace(ch)) {
                pendingSpace = true;
            } else {
                if (pendingSpace && !out.isEmpty()) {
                    out.append(' ');
                }
                pendingSpace = false;
                out.append(ch);
            }
        }
        return out.toString().strip();
    }

    static String identifierAt(String text, int start) {
        var i = start;
        while (i < text.length() && Character.isWhitespace(text.charAt(i))) {
            i++;
        }
        var out = new StringBuilder();
        var quoted = false;
        while (i < text.length()) {
            var ch = text.charAt(i);
            if (ch == '"') {
                quoted = !quoted;
                out.append(ch);
                i++;
            } else if (quoted || isIdentifierPart(ch) || ch == '.') {
                out.append(ch);
                i++;
            } else {
                break;
            }
        }
        return out.toString();
    }

    static boolean isIdentifierPart(char ch) {
        return Character.isLetterOrDigit(ch) || ch == '_' || ch == '$' || ch == '#' || ch == '"';
    }

    private enum State {
        NORMAL,
        STRING,
        LINE_COMMENT,
        BLOCK_COMMENT
    }
}
