# 뉴스 수집 DNS·404 복구 설계

기준: 2026-11-19 KST. 구현 전에 작성한다. 대상: 뉴스 수집만. 기존 데이터/원장/거래/ML 학습 로직은 변경하지 않는다.

## 1. 관측 근거

- runtime jobs의 `news:Reuters Business`, `news:Reuters World`가 `feeds.reuters.com` DNS 오류로 실패한다. 사용자 환경의 허용된 네트워크에서 DNS 실패를 재현했다.
- `https://home.treasury.gov/news/press-releases/rss`는 HTTP 404다.
- [Treasury 공식 보도자료 목록](https://home.treasury.gov/news/press-releases)은 HTTP 200 HTML을 반환한다. 본문의 `time[datetime]`, `h3.featured-stories__headline`과 공식 `/news/press-releases/<id>/` 링크를 확인했다. RSS 링크는 발견되지 않았다.
- Google News RSS의 `site:reuters.com/business when:7d`, `site:reuters.com/world when:7d` 쿼리는 각각 HTTP 200, RSS 2.0, 기사 100개를 반환했다. 항목의 `<source url="https://www.reuters.com">Reuters</source>`를 확인했다. Reuters 직접 RSS와 동일한 전달 방식이라고 표현하지 않는다.

## 2. 요구사항

| ID | 설계 | 완료 조건 |
|---|---|---|
| N1 | Reuters 소스 두 개를 발행사 제한 Google News RSS로 교체 | 기존 소스 이름/job key 유지; `source.href`의 HTTPS reuters.com 또는 그 하위 도메인만 채택; 다른 발행사/메타데이터 누락/유사 도메인 거부 |
| N2 | Treasury 전용 공식 목록 HTML 어댑터 | main 영역의 목록 제목·같은 항목 날짜·공식 원문 URL만 채택; 메뉴/분류/외부 링크 제외; 중복 링크 제거; 구조 변경은 오류로 처리 |
| N3 | 수집 출처 명시 | 이벤트와 성공 job details에 실제 수집 URL/전달 방식 기록; 기존 source/event_time/점수 규칙 유지; publication과 observed time 구분 |
| N4 | 가짜 성공 방지 | RSS 소스가 HTML 오류 페이지/파싱 불가 응답을 반환하면 실패; 유효한 빈 RSS는 정상 0건; 필터 결과 0건도 정상 |
| N5 | 제한된 테스트/운영 반영 | 수집 파서·scheduler 관련 테스트만 실행; 관련 변경 없음인 frontend는 로컬 재빌드 안 함; CI 일반 빌드 유지; 공개 수집 성공 후 기존 오류가 실제 성공으로 해소되는지 확인 |

## 3. 구조

`Source`에 기본값이 있는 `transport`와 `publisher_domain`을 추가한다. 기존 4인자 생성과 추가 RSS 설정은 호환된다. `_parse_source`는 동일한 timeout, 요청 1회, 기존 이벤트 정규화 경로를 유지한다. Treasury만 표준 라이브러리 `HTMLParser` 어댑터로 파싱하고, 일반 RSS는 feedparser를 사용한다. 새 의존성/인증/본문 크롤링은 필요 없다.

Google News RSS URL은 공통 URL 생성기를 재사용한다. source.href 호스트는 URL 파서로 검증하며 substring 검사나 제목의 'Reuters' 문자열만으로 신뢰하지 않는다. HTTPS 기사 링크만 저장한다. Reuters 전달 경로는 `google_news_rss`, Treasury는 `treasury_html`, 기존 RSS는 `rss`로 기록한다.

Treasury HTML은 main 내부 div의 time과 headline을 한 항목으로 매칭한다. 날짜가 없는 항목에 이전 날짜를 전파하지 않는다. 홈페이지 광고/메뉴의 유사 링크는 수집하지 않는다. 공식 보도자료 URL 호스트 및 경로를 검증하고 중복 제거 후 per_source 한도를 적용한다. 정확한 목록 구조를 찾지 못하면 ValueError로 실패를 노출한다. 기사 본문이나 임의 경로를 탐색하지 않는다.

원본 발행일은 `published`, 우리 시스템 최초 관측 시점은 기존 `event_time`으로 유지한다. 과거 예측을 소급 생성하지 않는다. source 이름은 보존하여 기존 job 오류를 삭제하지 않고 다음 성공 수집에서 error/failures가 자동 해소되도록 한다.

## 4. 테스트

고정 RSS/HTML fixture로 다음을 검증한다.

1. Reuters 외부 발행사·누락 출처·reuters.com.evil 유사 도메인 제외, 검증된 Reuters만 채택.
2. RSS HTML 오류 응답 거부, 정상 빈 RSS 및 정상 다른 RSS 호환.
3. Treasury 날짜/제목/원문 링크, 중복/메뉴/외부 링크 제외, 날짜 없는 항목 거부, 구조 불일치 실패.
4. timeout 전달 및 기존 수집 시간 제한/캐시 fallback 회귀.
5. 기존 실패 job 키 유지, 성공 후 오류 해소, 실패 지속 시 기존 재시도 유지. 경로 메타데이터 저장.

공개 smoke test는 세 복구 소스만 검사한다. 구현 후 running collector/API 프로세스를 새 코드로 재시작하고 `GET /api/runtime`에서 세 뉴스 job의 성공과 오류 해소를 확인한다. 기존 페이퍼 세션·잔고·원장을 보존한다. 검증을 위해 데이터/오류를 삭제하지 않는다.

## 5. 커밋·PR

이슈 생성 → fix/<issue>-news-source-recovery → 설계 MD 선행 커밋 → 구현/테스트 → 공개 수집 검증 → CI → 일반 merge. Conventional Commit과 저장소 PR 템플릿 준수. 전체 테스트/clean build는 수행하지 않는다. 리뷰 승인을 별도 병합 조건으로 추가하지 않는다.

## 6. 검증 기록

구현 후 실행 결과와 PR 링크를 추가한다.
