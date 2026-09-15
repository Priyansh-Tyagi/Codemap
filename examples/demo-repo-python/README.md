# demo-repo-python

The Python twin of `../demo-repo` (the JS demo app) - same architecture,
same deliberate circular dependency (`auth_service` <-> `user_service`),
same over-relied-on `validators` utility file, same route/controller/
service/model layering. Built to show CodeMap analyzing the same
application shape in two different languages.

Not a real, runnable Flask app - `router` is never actually defined
anywhere; this exists purely as static-analysis fixture data.
